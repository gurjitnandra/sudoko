"""Wallet related API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.core.exceptions import InsufficientCreditsError
from app.models.common import PaginationParams
from app.models.wallet import TransactionEntry, TransactionListResponse, WalletBalance
from app.services.wallet import WalletService

router = APIRouter()


def get_wallet_service() -> WalletService:
    return WalletService()


@router.get("/balance", response_model=WalletBalance)
async def get_balance(
    current_user=Depends(get_current_user),
    wallet_service: WalletService = Depends(get_wallet_service),
):
    balance = await wallet_service.get_balance(str(current_user["_id"]))
    return WalletBalance(balance=balance)


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    params: PaginationParams = Depends(),
    current_user=Depends(get_current_user),
    wallet_service: WalletService = Depends(get_wallet_service),
):
    results = await wallet_service.list_transactions(
        str(current_user["_id"]),
        limit=params.limit,
        cursor=params.cursor,
    )
    next_cursor = results[-1]["_id"] if results else None
    transactions = [
        TransactionEntry(
            transaction_id=doc["transaction_id"],
            type=doc["type"],
            amount=doc["amount"],
            game_id=str(doc["game_id"]) if doc.get("game_id") else None,
            timestamp=doc["timestamp"],
            status=doc["status"],
            notes=doc.get("notes"),
        )
        for doc in results
    ]
    return TransactionListResponse(
        transactions=transactions,
        next_cursor=str(next_cursor) if next_cursor else None,
    )


@router.post("/transfer")
async def internal_transfer(
    payload: dict,
    wallet_service: WalletService = Depends(get_wallet_service),
):
    target_id = payload.get("to_user_id")
    amount = payload.get("amount")
    reason = payload.get("reason", "manual_adjustment")
    if not target_id or not isinstance(amount, int):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    try:
        wallet = await wallet_service.credit(target_id, amount=amount, game_id=None, notes=reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "wallet": {
            "balance": wallet.get("balance"),
        }
    }
