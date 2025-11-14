"""
Image Processing Utility
Handles image upload, compression, and optimization
"""

import os
import secrets
from PIL import Image
from werkzeug.utils import secure_filename
from flask import current_app


def get_image_settings():
    """
    Get image processing settings from database

    Returns:
        dict: Image settings with defaults
    """
    try:
        from modules.auth.models import Settings

        return {
            'max_dimension': Settings.get_value('warehouse_image_max_dimension', 1600),
            'quality': Settings.get_value('warehouse_image_quality', 85),
            'dpi': Settings.get_value('warehouse_image_dpi', 72),
            'allowed_formats': Settings.get_value('warehouse_image_formats', 'jpg,jpeg,png,webp,gif'),
            'max_size_mb': Settings.get_value('warehouse_image_max_size_mb', 10),
            'max_per_product': Settings.get_value('warehouse_image_max_per_product', 10)
        }
    except Exception as e:
        # Fallback to defaults if settings not available
        current_app.logger.warning(f"Could not load image settings, using defaults: {str(e)}")
        return {
            'max_dimension': 1600,
            'quality': 85,
            'dpi': 72,
            'allowed_formats': 'jpg,jpeg,png,webp,gif',
            'max_size_mb': 10,
            'max_per_product': 10
        }


def allowed_file(filename):
    """
    Check if file extension is allowed based on settings

    Args:
        filename (str): Filename to check

    Returns:
        bool: True if allowed, False otherwise
    """
    if '.' not in filename:
        return False

    ext = filename.rsplit('.', 1)[1].lower()
    settings = get_image_settings()
    allowed_extensions = set(settings['allowed_formats'].split(','))

    return ext in allowed_extensions


def generate_unique_filename(original_filename):
    """
    Generate unique filename using secure random token

    Args:
        original_filename (str): Original filename

    Returns:
        str: Unique filename (token + extension)
    """
    ext = original_filename.rsplit('.', 1)[1].lower()
    token = secrets.token_urlsafe(16)
    return f"{token}.{ext}"


def compress_image(file_path, max_size=None, dpi=None, quality=None):
    """
    Compress and optimize image using settings from database

    Args:
        file_path (str): Path to image file
        max_size (int, optional): Maximum width/height in pixels (from settings if None)
        dpi (int, optional): DPI for web optimization (from settings if None)
        quality (int, optional): JPEG quality (1-100) (from settings if None)

    Returns:
        None (modifies file in place)
    """
    try:
        # Get settings if parameters not provided
        if max_size is None or dpi is None or quality is None:
            settings = get_image_settings()
            max_size = max_size or settings['max_dimension']
            dpi = dpi or settings['dpi']
            quality = quality or settings['quality']

        # Open image
        img = Image.open(file_path)

        # Convert RGBA to RGB if needed (for JPEG)
        if img.mode == 'RGBA':
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
            img = background

        # Get original size
        width, height = img.size

        # Calculate new size maintaining aspect ratio
        if width > max_size or height > max_size:
            if width > height:
                new_width = max_size
                new_height = int((max_size / width) * height)
            else:
                new_height = max_size
                new_width = int((max_size / height) * width)

            # Resize with high-quality resampling
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Save optimized image
        img.save(
            file_path,
            optimize=True,
            quality=quality,
            dpi=(dpi, dpi)
        )

    except Exception as e:
        current_app.logger.error(f"Error compressing image {file_path}: {str(e)}")
        raise


def process_upload(file, upload_folder):
    """
    Process uploaded file: validate, save original, create compressed version

    Args:
        file: FileStorage object from form
        upload_folder (str): Base upload folder path

    Returns:
        dict: {
            'filename': str,
            'path_original': str,
            'path_compressed': str
        }

    Raises:
        ValueError: If file is invalid or processing fails
    """
    # Validate file
    if not file or file.filename == '':
        raise ValueError('No file provided')

    if not allowed_file(file.filename):
        settings = get_image_settings()
        allowed_formats = settings['allowed_formats'].replace(',', ', ')
        raise ValueError(f'Invalid file type. Allowed types: {allowed_formats}')

    # Generate unique filename
    unique_filename = generate_unique_filename(file.filename)

    # Create paths
    original_folder = os.path.join(upload_folder, 'original')
    compressed_folder = os.path.join(upload_folder, 'compressed')

    # Ensure folders exist
    os.makedirs(original_folder, exist_ok=True)
    os.makedirs(compressed_folder, exist_ok=True)

    original_path = os.path.join(original_folder, unique_filename)
    compressed_path = os.path.join(compressed_folder, unique_filename)

    try:
        # Save original
        file.save(original_path)

        # Create compressed version
        # Copy original to compressed location first
        img = Image.open(original_path)
        img.save(compressed_path)

        # Compress
        compress_image(compressed_path)

        # Return relative paths (from static folder)
        return {
            'filename': unique_filename,
            'path_original': os.path.join('uploads', 'products', 'original', unique_filename),
            'path_compressed': os.path.join('uploads', 'products', 'compressed', unique_filename)
        }

    except Exception as e:
        # Clean up on error
        if os.path.exists(original_path):
            os.remove(original_path)
        if os.path.exists(compressed_path):
            os.remove(compressed_path)

        current_app.logger.error(f"Error processing upload: {str(e)}")
        raise ValueError(f'Error processing image: {str(e)}')


def delete_image_files(path_original, path_compressed):
    """
    Delete image files (original and compressed)

    Args:
        path_original (str): Relative path to original image
        path_compressed (str): Relative path to compressed image

    Returns:
        bool: True if deleted successfully, False otherwise
    """
    try:
        # Convert relative paths to absolute
        static_folder = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
        original_abs = os.path.join(static_folder, '..', path_original)
        compressed_abs = os.path.join(static_folder, '..', path_compressed)

        # Delete files if they exist
        if os.path.exists(original_abs):
            os.remove(original_abs)

        if os.path.exists(compressed_abs):
            os.remove(compressed_abs)

        return True

    except Exception as e:
        current_app.logger.error(f"Error deleting image files: {str(e)}")
        return False
