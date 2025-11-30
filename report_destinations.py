# report_destinations.py
"""
Report Destination Handlers

Manages exporting reports to various destinations:
- Network paths (UNC/Windows shares, Linux mounts)
- Email (SMTP with attachments)
- SFTP/FTP servers
- Cloud storage (S3, Azure Blob, Google Cloud Storage)
- SharePoint/OneDrive
"""

import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from io import BytesIO
import base64

from logger import log_info, log_error, log_warning


class DestinationError(Exception):
    """Custom exception for destination operations."""
    pass


class BaseDestination:
    """Base class for all destination handlers."""
    
    def __init__(self, config: Dict[str, Any]):
        self. config = config
        self.name = config.get("name", "Unnamed Destination")
    
    def validate_config(self) -> Tuple[bool, str]:
        """Validate the configuration.  Returns (is_valid, message)."""
        raise NotImplementedError
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test the connection to the destination.  Returns (success, message)."""
        raise NotImplementedError
    
    def send(self, filename: str, data: bytes, content_type: str) -> Tuple[bool, str]:
        """Send file to destination. Returns (success, message/path)."""
        raise NotImplementedError


class NetworkPathDestination(BaseDestination):
    """Handler for network path destinations (UNC paths, mounted drives)."""
    
    def validate_config(self) -> Tuple[bool, str]:
        path = self.config. get("path", ""). strip()
        if not path:
            return False, "Network path is required"
        return True, "Configuration valid"
    
    def test_connection(self) -> Tuple[bool, str]:
        path = self.config. get("path", "").strip()
        try:
            # Check if path exists
            if os.path.exists(path):
                # Try to write a test file
                test_file = os. path.join(path, f". test_{datetime.now(). timestamp()}")
                try:
                    with open(test_file, 'w') as f:
                        f.write("test")
                    os.remove(test_file)
                    return True, f"Successfully connected to {path}"
                except PermissionError:
                    return False, f"Permission denied for path: {path}"
                except Exception as e:
                    return False, f"Write test failed: {str(e)}"
            else:
                # Try to create the directory
                try:
                    os.makedirs(path, exist_ok=True)
                    return True, f"Path created: {path}"
                except Exception as e:
                    return False, f"Path does not exist and cannot be created: {str(e)}"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
    
    def send(self, filename: str, data: bytes, content_type: str) -> Tuple[bool, str]:
        path = self.config. get("path", "").strip()
        subfolder_pattern = self.config. get("subfolder_pattern", "")
        
        try:
            # Build subfolder based on pattern
            if subfolder_pattern:
                now = datetime.now()
                subfolder = subfolder_pattern.format(
                    year=now.year,
                    month=now.strftime("%m"),
                    day=now.strftime("%d"),
                    date=now.strftime("%Y-%m-%d"),
                    datetime=now.strftime("%Y%m%d_%H%M%S")
                )
                full_path = os. path.join(path, subfolder)
            else:
                full_path = path
            
            # Ensure directory exists
            os.makedirs(full_path, exist_ok=True)
            
            # Write file
            file_path = os. path.join(full_path, filename)
            with open(file_path, 'wb') as f:
                f. write(data)
            
            log_info(f"Report saved to network path: {file_path}")
            return True, file_path
            
        except Exception as e:
            log_error(f"Failed to save to network path: {str(e)}")
            return False, str(e)


class EmailDestination(BaseDestination):
    """Handler for email destinations with SMTP."""
    
    def validate_config(self) -> Tuple[bool, str]:
        required = ["smtp_host", "smtp_port", "recipients"]
        missing = [f for f in required if not self.config.get(f)]
        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"
        return True, "Configuration valid"
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            smtp_host = self. config.get("smtp_host")
            smtp_port = int(self.config. get("smtp_port", 587))
            use_tls = self.config.get("use_tls", True)
            username = self.config. get("username")
            password = self. config.get("password")
            
            if use_tls:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                server.starttls()
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            
            if username and password:
                server.login(username, password)
            
            server. quit()
            return True, f"Successfully connected to {smtp_host}:{smtp_port}"
            
        except Exception as e:
            return False, f"SMTP connection failed: {str(e)}"
    
    def send(self, filename: str, data: bytes, content_type: str) -> Tuple[bool, str]:
        try:
            smtp_host = self. config.get("smtp_host")
            smtp_port = int(self.config. get("smtp_port", 587))
            use_tls = self.config.get("use_tls", True)
            username = self.config. get("username")
            password = self. config.get("password")
            from_email = self. config.get("from_email", username)
            recipients = self.config. get("recipients", [])
            subject_template = self.config. get("subject", "Report: {filename}")
            body_template = self. config.get("body", "Please find the attached report.")
            
            if isinstance(recipients, str):
                recipients = [r.strip() for r in recipients.split(",")]
            
            # Build email
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject_template.format(
                filename=filename,
                date=datetime.now().strftime("%Y-%m-%d"),
                datetime=datetime.now().strftime("%Y-%m-%d %H:%M")
            )
            
            # Body
            body = body_template.format(
                filename=filename,
                date=datetime.now().strftime("%Y-%m-%d"),
                datetime=datetime.now(). strftime("%Y-%m-%d %H:%M")
            )
            msg. attach(MIMEText(body, 'plain'))
            
            # Attachment
            attachment = MIMEBase('application', 'octet-stream')
            attachment.set_payload(data)
            encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', f'attachment; filename="{filename}"')
            msg.attach(attachment)
            
            # Send
            if use_tls:
                server = smtplib. SMTP(smtp_host, smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(smtp_host, smtp_port)
            
            if username and password:
                server. login(username, password)
            
            server.sendmail(from_email, recipients, msg.as_string())
            server.quit()
            
            log_info(f"Report emailed to: {', '.join(recipients)}")
            return True, f"Sent to {', '. join(recipients)}"
            
        except Exception as e:
            log_error(f"Failed to send email: {str(e)}")
            return False, str(e)


class SFTPDestination(BaseDestination):
    """Handler for SFTP/FTP destinations."""
    
    def validate_config(self) -> Tuple[bool, str]:
        required = ["host", "username"]
        missing = [f for f in required if not self.config.get(f)]
        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"
        return True, "Configuration valid"
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            import paramiko
        except ImportError:
            return False, "paramiko library not installed.  Run: pip install paramiko"
        
        try:
            host = self.config. get("host")
            port = int(self. config.get("port", 22))
            username = self. config.get("username")
            password = self.config.get("password")
            private_key_path = self.config.get("private_key_path")
            
            transport = paramiko.Transport((host, port))
            
            if private_key_path:
                private_key = paramiko.RSAKey.from_private_key_file(private_key_path)
                transport.connect(username=username, pkey=private_key)
            else:
                transport.connect(username=username, password=password)
            
            sftp = paramiko.SFTPClient. from_transport(transport)
            sftp.listdir(".")  # Test listing
            sftp.close()
            transport.close()
            
            return True, f"Successfully connected to {host}:{port}"
            
        except Exception as e:
            return False, f"SFTP connection failed: {str(e)}"
    
    def send(self, filename: str, data: bytes, content_type: str) -> Tuple[bool, str]:
        try:
            import paramiko
        except ImportError:
            return False, "paramiko library not installed"
        
        try:
            host = self.config.get("host")
            port = int(self.config.get("port", 22))
            username = self.config.get("username")
            password = self.config. get("password")
            private_key_path = self.config.get("private_key_path")
            remote_path = self. config.get("remote_path", "/")
            
            transport = paramiko.Transport((host, port))
            
            if private_key_path:
                private_key = paramiko. RSAKey.from_private_key_file(private_key_path)
                transport.connect(username=username, pkey=private_key)
            else:
                transport.connect(username=username, password=password)
            
            sftp = paramiko.SFTPClient.from_transport(transport)
            
            # Build remote file path
            remote_file = os.path. join(remote_path, filename). replace("\\", "/")
            
            # Create remote directory if needed
            try:
                sftp.stat(remote_path)
            except FileNotFoundError:
                # Create directory recursively
                dirs = remote_path. split("/")
                current = ""
                for d in dirs:
                    if d:
                        current += f"/{d}"
                        try:
                            sftp.stat(current)
                        except FileNotFoundError:
                            sftp.mkdir(current)
            
            # Upload file
            with sftp.open(remote_file, 'wb') as f:
                f.write(data)
            
            sftp. close()
            transport.close()
            
            log_info(f"Report uploaded via SFTP to: {host}:{remote_file}")
            return True, f"{host}:{remote_file}"
            
        except Exception as e:
            log_error(f"SFTP upload failed: {str(e)}")
            return False, str(e)


class S3Destination(BaseDestination):
    """Handler for AWS S3 destinations."""
    
    def validate_config(self) -> Tuple[bool, str]:
        required = ["bucket_name", "region"]
        missing = [f for f in required if not self.config.get(f)]
        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"
        return True, "Configuration valid"
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            import boto3
        except ImportError:
            return False, "boto3 library not installed.  Run: pip install boto3"
        
        try:
            bucket_name = self.config.get("bucket_name")
            region = self. config.get("region")
            access_key = self. config.get("access_key_id")
            secret_key = self. config.get("secret_access_key")
            
            if access_key and secret_key:
                s3 = boto3.client(
                    's3',
                    region_name=region,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key
                )
            else:
                # Use default credentials (IAM role, env vars, etc.)
                s3 = boto3.client('s3', region_name=region)
            
            s3.head_bucket(Bucket=bucket_name)
            return True, f"Successfully connected to S3 bucket: {bucket_name}"
            
        except Exception as e:
            return False, f"S3 connection failed: {str(e)}"
    
    def send(self, filename: str, data: bytes, content_type: str) -> Tuple[bool, str]:
        try:
            import boto3
        except ImportError:
            return False, "boto3 library not installed"
        
        try:
            bucket_name = self.config. get("bucket_name")
            region = self.config.get("region")
            access_key = self.config.get("access_key_id")
            secret_key = self.config.get("secret_access_key")
            prefix = self.config. get("prefix", "reports/")
            
            if access_key and secret_key:
                s3 = boto3.client(
                    's3',
                    region_name=region,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key
                )
            else:
                s3 = boto3.client('s3', region_name=region)
            
            # Build S3 key with date-based prefix
            now = datetime.now()
            key = f"{prefix}{now.strftime('%Y/%m/%d/')}{filename}"
            
            s3. put_object(
                Bucket=bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type
            )
            
            s3_path = f"s3://{bucket_name}/{key}"
            log_info(f"Report uploaded to S3: {s3_path}")
            return True, s3_path
            
        except Exception as e:
            log_error(f"S3 upload failed: {str(e)}")
            return False, str(e)


class AzureBlobDestination(BaseDestination):
    """Handler for Azure Blob Storage destinations."""
    
    def validate_config(self) -> Tuple[bool, str]:
        if not self.config. get("connection_string") and not self.config. get("account_name"):
            return False, "Either connection_string or account_name is required"
        if not self.config. get("container_name"):
            return False, "container_name is required"
        return True, "Configuration valid"
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError:
            return False, "azure-storage-blob library not installed. Run: pip install azure-storage-blob"
        
        try:
            connection_string = self. config.get("connection_string")
            container_name = self. config.get("container_name")
            
            blob_service = BlobServiceClient. from_connection_string(connection_string)
            container_client = blob_service. get_container_client(container_name)
            container_client.get_container_properties()
            
            return True, f"Successfully connected to Azure container: {container_name}"
            
        except Exception as e:
            return False, f"Azure connection failed: {str(e)}"
    
    def send(self, filename: str, data: bytes, content_type: str) -> Tuple[bool, str]:
        try:
            from azure.storage.blob import BlobServiceClient, ContentSettings
        except ImportError:
            return False, "azure-storage-blob library not installed"
        
        try:
            connection_string = self. config.get("connection_string")
            container_name = self.config.get("container_name")
            prefix = self.config. get("prefix", "reports/")
            
            blob_service = BlobServiceClient.from_connection_string(connection_string)
            container_client = blob_service.get_container_client(container_name)
            
            # Build blob path
            now = datetime.now()
            blob_path = f"{prefix}{now.strftime('%Y/%m/%d/')}{filename}"
            
            blob_client = container_client.get_blob_client(blob_path)
            blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type)
            )
            
            full_path = f"azure://{container_name}/{blob_path}"
            log_info(f"Report uploaded to Azure: {full_path}")
            return True, full_path
            
        except Exception as e:
            log_error(f"Azure upload failed: {str(e)}")
            return False, str(e)


# =============================================================================
# DESTINATION FACTORY
# =============================================================================

DESTINATION_HANDLERS = {
    "network": NetworkPathDestination,
    "email": EmailDestination,
    "sftp": SFTPDestination,
    "ftp": SFTPDestination,  # Alias
    "s3": S3Destination,
    "aws_s3": S3Destination,  # Alias
    "azure": AzureBlobDestination,
    "azure_blob": AzureBlobDestination,  # Alias
}


def get_destination_handler(destination_type: str, config: Dict[str, Any]) -> BaseDestination:
    """Factory function to get the appropriate destination handler."""
    handler_class = DESTINATION_HANDLERS.get(destination_type. lower())
    if not handler_class:
        raise DestinationError(f"Unknown destination type: {destination_type}")
    return handler_class(config)


def send_report_to_destinations(
    report_name: str,
    data_by_format: Dict[str, bytes],
    destinations: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Send report to multiple destinations.
    
    Args:
        report_name: Base name for the report file
        data_by_format: Dict of format -> bytes (e.g., {"xlsx": bytes, "pdf": bytes})
        destinations: List of destination configurations
    
    Returns:
        List of result dictionaries with status and details
    """
    results = []
    timestamp = datetime.now(). strftime("%Y%m%d_%H%M%S")
    
    content_types = {
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
        "json": "application/json",
        "xml": "application/xml",
        "html": "text/html"
    }
    
    for dest_config in destinations:
        dest_type = dest_config.get("type", ""). lower()
        dest_name = dest_config. get("name", dest_type)
        formats_to_send = dest_config.get("formats", list(data_by_format.keys()))
        
        if isinstance(formats_to_send, str):
            formats_to_send = [f.strip() for f in formats_to_send.split(",")]
        
        try:
            handler = get_destination_handler(dest_type, dest_config)
            
            # Validate config
            valid, msg = handler.validate_config()
            if not valid:
                results.append({
                    "destination": dest_name,
                    "type": dest_type,
                    "success": False,
                    "error": f"Invalid configuration: {msg}"
                })
                continue
            
            # Send each format
            for fmt in formats_to_send:
                if fmt not in data_by_format:
                    continue
                
                filename = f"{report_name}_{timestamp}.{fmt}"
                content_type = content_types.get(fmt, "application/octet-stream")
                
                success, result_msg = handler.send(filename, data_by_format[fmt], content_type)
                results.append({
                    "destination": dest_name,
                    "type": dest_type,
                    "format": fmt,
                    "filename": filename,
                    "success": success,
                    "path": result_msg if success else None,
                    "error": None if success else result_msg
                })
                
        except Exception as e:
            results.append({
                "destination": dest_name,
                "type": dest_type,
                "success": False,
                "error": str(e)
            })
    
    return results