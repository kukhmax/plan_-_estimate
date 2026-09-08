from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Witaj w Plan & Estimate!\n"
        "Aplikacja do zarządzania pracami remontowo-wykończeniowymi."
    )
