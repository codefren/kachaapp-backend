#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para enviar archivos Excel por correo electrónico.
"""
import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime


# Configuración SMTP
SMTP_CONFIG = {
    'host': 'smtp.office365.com',
    'port': 587,
    'user': 'notificaciones@tockcontrol.com',
    'password': 'Rr9B4e7DFJIxz58K4lLR',
    'from_email': 'Notificaciones TockControl <notificaciones@tockcontrol.com>',
    'use_tls': True
}


def send_excel_email(
    to_email,
    excel_file,
    subject=None,
    body=None,
    purchase_order_id=None
):
    """
    Envía un archivo Excel por correo electrónico.
    
    Args:
        to_email: Email del destinatario
        excel_file: Ruta al archivo Excel
        subject: Asunto del correo (opcional)
        body: Cuerpo del mensaje (opcional)
        purchase_order_id: ID del PurchaseOrder para referencia (opcional)
    """
    
    print(f"\n{'='*70}")
    print("ENVIANDO EXCEL POR CORREO ELECTRÓNICO")
    print(f"{'='*70}\n")
    
    # Verificar que el archivo existe
    if not os.path.exists(excel_file):
        print(f"❌ Error: No se encontró el archivo {excel_file}")
        return False
    
    file_size = os.path.getsize(excel_file) / 1024  # KB
    print(f"📎 Archivo: {excel_file}")
    print(f"   Tamaño: {file_size:.2f} KB")
    
    # Preparar asunto y cuerpo por defecto
    if not subject:
        if purchase_order_id:
            subject = f"Purchase Order #{purchase_order_id} - Pedido Actualizado"
        else:
            subject = f"Pedido - {os.path.basename(excel_file)}"
    
    if not body:
        body = f"""
Hola,

Adjunto encontrarás el archivo Excel con el pedido actualizado.

Archivo: {os.path.basename(excel_file)}
Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}
"""
        if purchase_order_id:
            body += f"Purchase Order ID: #{purchase_order_id}\n"
        
        body += """
Saludos,
TockControl
"""
    
    print(f"📧 De: {SMTP_CONFIG['from_email']}")
    print(f"📨 Para: {to_email}")
    print(f"📋 Asunto: {subject}")
    
    try:
        # Crear mensaje
        msg = MIMEMultipart()
        msg['From'] = SMTP_CONFIG['from_email']
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Adjuntar cuerpo del mensaje
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Adjuntar archivo Excel
        with open(excel_file, 'rb') as f:
            part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename={os.path.basename(excel_file)}'
            )
            msg.attach(part)
        
        print(f"\n🔄 Conectando a {SMTP_CONFIG['host']}:{SMTP_CONFIG['port']}...")
        
        # Conectar y enviar (con timeout de 30 segundos)
        with smtplib.SMTP(SMTP_CONFIG['host'], SMTP_CONFIG['port'], timeout=30) as server:
            if SMTP_CONFIG['use_tls']:
                server.starttls()
                print("   ✓ Conexión TLS establecida")
            
            print(f"   🔐 Autenticando como {SMTP_CONFIG['user']}...")
            server.login(SMTP_CONFIG['user'], SMTP_CONFIG['password'])
            print("   ✓ Autenticación exitosa")
            
            print(f"   📤 Enviando correo...")
            server.send_message(msg)
            print("   ✓ Correo enviado")
        
        print(f"\n{'='*70}")
        print(f"✅ EMAIL ENVIADO EXITOSAMENTE")
        print(f"{'='*70}\n")
        return True
        
    except smtplib.SMTPAuthenticationError:
        print("\n❌ Error: Fallo en la autenticación SMTP")
        print("   Verifica el usuario y contraseña")
        return False
    except smtplib.SMTPConnectError as e:
        print(f"\n❌ Error: No se pudo conectar al servidor SMTP")
        print(f"   Detalles: {e}")
        return False
    except TimeoutError:
        print("\n❌ Error: Timeout al conectar al servidor SMTP")
        print("   Verifica tu conexión a internet o firewall")
        return False
    except smtplib.SMTPException as e:
        print(f"\n❌ Error SMTP: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Función principal."""
    print("\n" + "="*70)
    print("ENVIAR EXCEL POR CORREO ELECTRÓNICO")
    print("="*70)
    
    # Obtener parámetros
    if len(sys.argv) >= 3:
        excel_file = sys.argv[1]
        to_email = sys.argv[2]
        purchase_order_id = sys.argv[3] if len(sys.argv) > 3 else None
    else:
        # Modo interactivo
        print("\nArchivos Excel disponibles:")
        excel_files = [f for f in os.listdir('.') if f.endswith('.xlsx')]
        if excel_files:
            for i, f in enumerate(excel_files, 1):
                size = os.path.getsize(f) / 1024
                print(f"   {i}. {f} ({size:.2f} KB)")
            print()
        
        excel_file = input("Archivo Excel a enviar: ").strip()
        if not excel_file:
            print("❌ Debes especificar un archivo")
            return
        
        to_email = input("Email del destinatario: ").strip()
        if not to_email:
            print("❌ Debes especificar un email")
            return
        
        purchase_order_id = input("ID del Purchase Order (opcional, Enter para omitir): ").strip()
        purchase_order_id = purchase_order_id if purchase_order_id else None
    
    # Enviar email
    success = send_excel_email(
        to_email=to_email,
        excel_file=excel_file,
        purchase_order_id=purchase_order_id
    )
    
    if success:
        print("✅ Proceso completado exitosamente!\n")
    else:
        print("❌ El proceso terminó con errores\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
