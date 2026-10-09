"""The catalogues of the contract and the protocols (Stage 16B.3), read only: the screens of the questionnaire, the premises
requirements and the acceptance regulation draw what the server says. The content is the same for every owner."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.domain.contracts.catalog import (
    ContractCatalog,
    ContractCatalogError,
    load_contract_catalog,
)
from app.models.user import User

router = APIRouter()


@router.get("/contract-catalog", response_model=ContractCatalog, summary="Catalogues of the contract and the protocols")
async def read_contract_catalog(current_user: User = Depends(get_current_user)) -> ContractCatalog:
    try:
        return load_contract_catalog()
    except ContractCatalogError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Catalogue is not available") from exc
