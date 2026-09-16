"""
End of Day (EOD) Operations & Reconciliation.
Ensures perfect double-entry ledger integrity across all client accounts.
"""

from decimal import Decimal
from celery import shared_task
from sqlalchemy import select, func

from src.core.database import AsyncSessionFactory
from src.core.exceptions import DoubleEntryLedgerMismatchError
from src.portfolio.models import Account, LedgerEntry, LedgerJournal
from tasks.worker import run_async


async def _reconcile_ledgers_async() -> list[str]:
    """
    Verifies that sum(LedgerEntries) == Account.cash_balance for every account.
    If a mismatch is found, a catastrophic domain exception is raised.
    """
    mismatches: list[str] = []

    async with AsyncSessionFactory() as session:
        # Fetch all active accounts
        stmt = select(Account)
        result = await session.execute(stmt)
        accounts = result.scalars().all()

        for account in accounts:
            # Aggregate all historical cash flows from the immutable double-entry ledger
            ledger_summation_stmt = (
                select(func.sum(LedgerEntry.amount))
                .join(LedgerJournal, LedgerJournal.id == LedgerEntry.journal_id)
                .where(
                    LedgerJournal.account_id == account.id
                )
            )
            ledger_result = await session.execute(ledger_summation_stmt)
            total_settled_funds = ledger_result.scalar() or Decimal("0.0")

            # Validate fast-read synchronization
            if account.cash_balance != total_settled_funds:
                mismatch_msg = (
                    f"Account {account.id}: Fast-read balance {account.cash_balance} "
                    f"DOES NOT MATCH immutable ledger {total_settled_funds}."
                )
                mismatches.append(mismatch_msg)

        if mismatches:
            # CRITICAL FAILURE: The platform's accounting is corrupt.
            # In a live system, this triggers PagerDuty for the engineering executives.
            error_details = " | ".join(mismatches)
            raise DoubleEntryLedgerMismatchError(
                message="End of Day Reconciliation FAILED. Ledger integrity compromised.",
                details={"mismatches": error_details}
            )

        return [str(a.id) for a in accounts]


@shared_task(name="tasks.eod_reconciliation", time_limit=3600)
@run_async
async def run_eod_reconciliation() -> dict[str, Any]:
    """
    Celery task entrypoint for daily reconciliation.
    Typically scheduled at 17:00 EST.
    """
    reconciled_account_ids = await _reconcile_ledgers_async()
    return {
        "status": "success", 
        "reconciled_accounts_count": len(reconciled_account_ids)
    }