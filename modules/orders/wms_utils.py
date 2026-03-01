"""
WMS Utilities — Packaging Suggestion Algorithm
================================================

Provides suggest_packaging(order) which analyzes order items' dimensions/weight
and returns ranked packaging material suggestions.
"""

from modules.orders.wms_models import PackagingMaterial


def suggest_packaging(order):
    """
    Analyze order items and suggest best-fit packaging materials.

    Returns dict with keys:
      - suggestions: list of top 3 material dicts (sorted by fit_score desc, cost asc)
      - warnings: list of warning strings
      - total_weight: total product weight in kg (float)
      - total_volume: total needed volume in cm³ (float)
    """
    items = order.items or []

    if not items:
        return {
            'suggestions': [],
            'warnings': ['Zamówienie nie ma pozycji'],
            'total_weight': 0,
            'total_volume': 0,
        }

    # 1. Collect product data
    warnings = []
    total_weight = 0.0
    total_volume = 0.0
    max_dimensions = []  # list of sorted [l, w, h] per item
    items_without_dims = 0
    items_without_weight = 0

    for item in items:
        product = item.product
        qty = item.quantity or 1

        # Weight
        if product and product.weight:
            total_weight += float(product.weight) * qty
        else:
            items_without_weight += 1

        # Dimensions
        if product and product.length and product.width and product.height:
            l = float(product.length)
            w = float(product.width)
            h = float(product.height)
            total_volume += l * w * h * qty
            # Track max single-item dimensions for fit check
            dims_sorted = sorted([l, w, h], reverse=True)
            for _ in range(qty):
                max_dimensions.append(dims_sorted)
        else:
            items_without_dims += 1

    if items_without_dims > 0:
        warnings.append(f'{items_without_dims} {"produkt nie ma" if items_without_dims == 1 else "produktów nie ma"} wymiarów')
    if items_without_weight > 0:
        warnings.append(f'{items_without_weight} {"produkt nie ma" if items_without_weight == 1 else "produktów nie ma"} wagi')

    # 2. Add 30% buffer for protective material
    needed_volume = total_volume * 1.3

    # 3. Get the largest single-item dimensions (for fit check)
    if max_dimensions:
        overall_max = [
            max(d[0] for d in max_dimensions),
            max(d[1] for d in max_dimensions),
            max(d[2] for d in max_dimensions),
        ]
    else:
        overall_max = None

    # 4. Filter active materials with stock
    materials = PackagingMaterial.query.filter(
        PackagingMaterial.is_active == True,
        PackagingMaterial.quantity_in_stock > 0,
    ).order_by(PackagingMaterial.sort_order).all()

    if not materials:
        return {
            'suggestions': [],
            'warnings': warnings + ['Brak dostępnych materiałów pakowania'],
            'total_weight': round(total_weight, 2),
            'total_volume': round(needed_volume, 2),
        }

    # 5. Score each material
    scored = []
    has_product_dims = items_without_dims < len(items)

    for mat in materials:
        mat_volume = mat.inner_volume  # None if no dimensions
        mat_max_weight = float(mat.max_weight) if mat.max_weight else None

        # Weight check
        if mat_max_weight is not None and total_weight > 0 and total_weight > mat_max_weight:
            continue  # Too heavy

        # Dimension fit check
        fits_dimensions = True
        if mat_volume is not None and has_product_dims:
            # Volume check
            if mat_volume < needed_volume:
                fits_dimensions = False

            # Individual dimension check (with rotation)
            if fits_dimensions and overall_max is not None:
                mat_dims = sorted([
                    float(mat.inner_length),
                    float(mat.inner_width),
                    float(mat.inner_height),
                ], reverse=True)
                # Each sorted dimension of the product must fit
                for i in range(3):
                    if overall_max[i] > mat_dims[i]:
                        fits_dimensions = False
                        break

        # Materials without dimensions (e.g. foliopak) — always pass with low score
        if mat_volume is None:
            fit_score = 0.2  # Low default score
        elif not has_product_dims:
            # No product dims — all materials with dimensions get medium score
            fit_score = 0.5
        elif not fits_dimensions:
            continue  # Doesn't fit
        else:
            # Calculate fit score: smaller volume difference = better
            volume_diff = mat_volume - needed_volume
            fit_score = max(0.0, min(1.0, 1.0 - (volume_diff / mat_volume)))

        scored.append({
            'material': mat,
            'fit_score': round(fit_score, 2),
        })

    # 6. Sort: highest fit_score first, then lowest cost
    scored.sort(key=lambda x: (
        -x['fit_score'],
        float(x['material'].cost) if x['material'].cost else 999999,
    ))

    # 7. Take top 3
    top = scored[:3]

    suggestions = []
    for entry in top:
        mat = entry['material']
        suggestions.append({
            'id': mat.id,
            'name': mat.name,
            'type': mat.type,
            'type_display': mat.type_display,
            'dimensions_display': mat.dimensions_display,
            'fit_score': entry['fit_score'],
            'own_weight': float(mat.own_weight) if mat.own_weight else None,
            'cost': float(mat.cost) if mat.cost else None,
            'quantity_in_stock': mat.quantity_in_stock,
            'is_low_stock': mat.is_low_stock,
        })

    return {
        'suggestions': suggestions,
        'warnings': warnings,
        'total_weight': round(total_weight, 2),
        'total_volume': round(needed_volume, 2),
    }
