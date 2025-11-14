"""
Price Calculation Utilities
Handles price rounding and calculations
"""

from flask import current_app


def round_price(price, rounding_mode=None):
    """
    Round price according to warehouse settings

    Args:
        price (float): Price to round
        rounding_mode (str, optional): 'full' or 'decimal'. If None, reads from settings.

    Returns:
        float: Rounded price

    Examples:
        round_price(45.67, 'full') -> 46.00
        round_price(45.67, 'decimal') -> 45.99
        round_price(45.23, 'full') -> 45.00
        round_price(45.23, 'decimal') -> 45.49
    """

    if price is None or price == 0:
        return 0.0

    # Get rounding mode from settings if not provided
    if rounding_mode is None:
        try:
            from modules.auth.models import Settings
            rounding_mode = Settings.get_value('warehouse_price_rounding', 'full')
        except Exception as e:
            current_app.logger.warning(f"Could not load price_rounding setting, using default 'full': {str(e)}")
            rounding_mode = 'full'

    price = float(price)

    if rounding_mode == 'full':
        # Round to full złoty (np. 45.67 → 46.00, 45.23 → 45.00)
        return round(price)

    elif rounding_mode == 'decimal':
        # Round to .49 or .99 (psychological pricing)
        # Examples:
        #   45.23 → 45.49
        #   45.67 → 45.99
        #   45.50-45.99 → 45.99
        #   45.00-45.49 → 45.49

        whole = int(price)
        decimal = price - whole

        if decimal < 0.50:
            return float(f"{whole}.49")
        else:
            return float(f"{whole}.99")

    else:
        # Fallback: no rounding
        current_app.logger.warning(f"Unknown rounding mode '{rounding_mode}', returning original price")
        return round(price, 2)


def calculate_margin_percentage(sale_price, purchase_price):
    """
    Calculate margin percentage

    Args:
        sale_price (float): Sale price in PLN
        purchase_price (float): Purchase price in PLN

    Returns:
        float: Margin percentage (rounded to 2 decimal places)
        None: If purchase_price is 0 or None

    Formula:
        margin % = ((sale_price - purchase_price) / purchase_price) * 100

    Example:
        sale_price = 100 PLN
        purchase_price = 70 PLN
        margin = ((100 - 70) / 70) * 100 = 42.86%
    """

    if not purchase_price or purchase_price == 0:
        return None

    margin = ((float(sale_price) - float(purchase_price)) / float(purchase_price)) * 100
    return round(margin, 2)


def calculate_sale_price_from_margin(purchase_price, margin_percentage):
    """
    Calculate sale price from purchase price and desired margin

    Args:
        purchase_price (float): Purchase price in PLN
        margin_percentage (float): Desired margin percentage

    Returns:
        float: Calculated sale price (before rounding)

    Formula:
        sale_price = purchase_price * (1 + margin_percentage / 100)

    Example:
        purchase_price = 70 PLN
        margin_percentage = 42.86%
        sale_price = 70 * (1 + 42.86/100) = 100 PLN
    """

    if not purchase_price or purchase_price == 0:
        return 0.0

    if not margin_percentage:
        margin_percentage = 0

    sale_price = float(purchase_price) * (1 + float(margin_percentage) / 100)
    return sale_price


def apply_margin_and_round(purchase_price, margin_percentage, rounding_mode=None):
    """
    Calculate sale price from purchase price and margin, then apply rounding

    Args:
        purchase_price (float): Purchase price in PLN
        margin_percentage (float): Desired margin percentage
        rounding_mode (str, optional): 'full' or 'decimal'. If None, reads from settings.

    Returns:
        float: Final sale price (after margin calculation and rounding)

    Example:
        purchase_price = 70 PLN
        margin_percentage = 42.86%
        rounding_mode = 'decimal'

        Step 1: Calculate sale price = 70 * (1 + 42.86/100) = 100 PLN
        Step 2: Round = 100.99 PLN
    """

    # Calculate sale price from margin
    sale_price = calculate_sale_price_from_margin(purchase_price, margin_percentage)

    # Apply rounding
    return round_price(sale_price, rounding_mode)
