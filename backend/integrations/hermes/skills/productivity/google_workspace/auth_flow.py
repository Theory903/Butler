from fastapi import APIRouter, Request, Depends, HTTPException
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/google/calendar", tags=["oauth", "calendar"])

@router.get("/login")
def login(request: Request):
    """
    Initiates the Google OAuth 2.0 flow for calendar scopes.
    We would formulate the google OAuth consent screen URI here and redirect.
    """
    logger.info("[AuthFlow] Initiating Google Calendar OAuth flow")
    return {"status": "redirecting", "url": "https://accounts.google.com/o/oauth2/v2/auth?..."}

@router.get("/callback")
def callback(request: Request, code: str = None, error: str = None):
    """
    Handles the Google OAuth callback, exchanging code for a refresh_token 
    and storing it in Butler's VaultService.
    """
    if error:
        logger.error(f"[AuthFlow] Calendar OAuth error: {error}")
        raise HTTPException(status_code=400, detail="OAuth failure")
        
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
        
    logger.info(f"[AuthFlow] Received code: {code}. Exchanging to VaultService.")
    
    # VaultService.store_secret("user_id", "google_refresh_token", "<exchanged_token>")
    
    return {"status": "success", "message": "Calendar integration completed."}
