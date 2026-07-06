from datetime import datetime, timedelta
import logging
import os
import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import httpx
import secrets

from api.database import get_db
from api.models import User, PWDResetOTP
from api.schemas import (
    UserCreate,
    UserResponse,
    Token,
    ForgotPasswordRequest,
    VerifyOTPRequest,
    ResetPasswordRequest,
    GoogleLoginRequest,
)
from api.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_reset_token,
    get_reset_password_email,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


def sync_send_otp_email(email: str, otp: str):
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_sender = os.getenv("SMTP_SENDER", smtp_username)

    if not smtp_host or not smtp_username:
        logger.warning(
            "\n"
            "========================================================\n"
            "SMTP NOT CONFIGURED. PRINTING PASSWORD RESET OTP:\n"
            f"Email: {email}\n"
            f"OTP Code: {otp}\n"
            "========================================================\n"
        )
        return

    msg = MIMEMultipart()
    msg["From"] = smtp_sender
    msg["To"] = email
    msg["Subject"] = "FitVision - Password Reset OTP"

    body = f"""
    <h2>FitVision Password Reset</h2>
    <p>We received a request to reset your password. Use the following 6-digit OTP code to verify your identity:</p>
    <h1 style="color: #E2A000; font-size: 32px; letter-spacing: 2px;">{otp}</h1>
    <p>This code will expire in 5 minutes.</p>
    <p>If you did not request this, please ignore this email.</p>
    """
    msg.attach(MIMEText(body, "html"))

    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_sender, email, msg.as_string())
        server.quit()
        logger.info(f"Successfully sent password reset OTP to {email}")
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
        logger.warning(f"FALLBACK OTP PRINT FOR {email}: {otp}")


async def send_otp_email(email: str, otp: str):
    await run_in_threadpool(sync_send_otp_email, email, otp)


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if username exists
    username_result = await db.execute(select(User).where(User.username == user_data.username))
    if username_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )

    # Check if email exists
    email_result = await db.execute(select(User).where(User.email == user_data.email))
    if email_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        gender=user_data.gender,
        date_of_birth=user_data.date_of_birth
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # Support checking either username or email in the 'username' field
    result = await db.execute(
        select(User).where(
            (User.username == form_data.username) | (User.email == form_data.username)
        )
    )
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalars().first()
    if not user:
        # Prevent user enumeration but log for developer convenience
        logger.info(f"Forgot password requested for non-existent email: {request.email}")
        return {"message": "If the email is registered, a password reset OTP has been sent."}

    # Generate 6-digit OTP
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    # Delete any existing OTP for this email
    await db.execute(delete(PWDResetOTP).where(PWDResetOTP.email == request.email))

    new_otp = PWDResetOTP(
        email=request.email,
        otp_code=otp_code,
        expires_at=expires_at
    )
    db.add(new_otp)
    await db.commit()

    # Send email asynchronously using threadpool
    await send_otp_email(request.email, otp_code)

    return {"message": "If the email is registered, a password reset OTP has been sent."}


@router.post("/verify-otp")
async def verify_otp(
    request: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(PWDResetOTP).where(PWDResetOTP.email == request.email))
    otp_record = result.scalars().first()

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP requested for this email."
        )

    if otp_record.expires_at < datetime.utcnow():
        await db.delete(otp_record)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired."
        )

    if otp_record.otp_code != request.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect OTP code."
        )

    # Valid OTP - clean it up immediately
    await db.delete(otp_record)
    await db.commit()

    # Return a temporary token for resetting password
    reset_token = create_reset_token(request.email)
    return {
        "reset_token": reset_token,
        "token_type": "bearer",
        "message": "OTP verified successfully. You can now reset your password."
    }


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match."
        )

    # Validate complexity matching Figma:
    # - At least 8 characters
    # - Contains an upper case letter
    # - Contains a symbol or a number
    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long."
        )
    if not any(c.isupper() for c in request.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter."
        )
    if not any(c.isdigit() or not c.isalnum() for c in request.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one number or special symbol."
        )

    # Decode reset token to get email
    email = get_reset_password_email(request.token)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    user.hashed_password = hash_password(request.password)
    await db.commit()

    return {"message": "Password has been reset successfully."}


@router.post("/google", response_model=Token)
async def google_login(request: GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
    # 1. Validate ID token via Google Tokeninfo endpoint
    token_info_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={request.id_token}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(token_info_url)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Google ID token"
                )
            payload = response.json()
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Google token verification failed: {str(e)}"
            )

    # 2. Extract email from Google payload
    email = payload.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google ID token does not contain email"
        )

    # 3. Check if user already exists
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if not user:
        # User does not exist, automatically register them
        email_prefix = email.split("@")[0]
        username = email_prefix[:40]
        
        # Ensure unique username
        user_check = await db.execute(select(User).where(User.username == username))
        if user_check.scalars().first():
            username = f"{username}_{secrets.token_hex(3)}"

        # Generate a random password for Google-authenticated user
        random_password = secrets.token_urlsafe(16)

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(random_password),
            gender=None,
            date_of_birth=None
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # 4. Generate FitVision access token
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


