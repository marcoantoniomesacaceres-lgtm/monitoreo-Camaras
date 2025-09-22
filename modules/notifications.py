import logging
import smtplib
from email.mime.text import MIMEText

# Importa configuración desde tu archivo config.py
from config import SMTP_SERVER, SMTP_PORT, EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER

logger = logging.getLogger("notifications")

def send_email(subject: str, body: str) -> bool:
    """
    Envía un correo usando SMTP.
    Devuelve True si se envió con éxito, False si falló.
    """
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, [EMAIL_RECEIVER], msg.as_string())
        logger.info(f"[EMAIL SENT] Subject: {subject}, To: {EMAIL_RECEIVER}")
        return True
    except Exception as e:
        logger.error(f"❌ Error enviando correo: {e}")
        return False


def notify(data: dict):
    """
    API principal de notificaciones.
    1. Intenta enviar email con el status de la cámara.
    2. Si falla, registra en logs para no interrumpir el sistema.
    """
    subject = f"Notificación - Cámara: {data.get('camera_status', 'desconocido')}"
    body = f"Detalles: {data}"

    success = send_email(subject, body)

    if not success:
        logger.warning(f"[FALLBACK LOG] {data}")
        print(f"[FALLBACK LOG] {data}")  # útil en desarrollo


def send(data: dict):
    """
    Alias de notify para compatibilidad con otros módulos y tests.
    """
    notify(data) 