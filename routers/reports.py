from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from auth import get_current_user
from reports.daily_report import generate_daily_report
from reports.weekly_report import generate_weekly_report
from reports.monthly_report import generate_monthly_report

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/daily")
async def daily_report():
    path = generate_daily_report()
    return FileResponse(path, media_type="application/pdf", filename="daily_report.pdf")

@router.get("/weekly")
async def weekly_report():
    path = generate_weekly_report()
    return FileResponse(path, media_type="application/pdf", filename="weekly_report.pdf")

@router.get("/monthly")
async def monthly_report():
    path = generate_monthly_report()
    return FileResponse(path, media_type="application/pdf", filename="monthly_report.pdf")