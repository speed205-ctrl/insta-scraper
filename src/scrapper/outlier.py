"""
Outlier detection module for calculating baseline performance and identifying viral content.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from scrapper.config import settings

logger = logging.getLogger(__name__)


def calculate_median_views(views: List[int]) -> int:
    """
    Calculate the statistical median of a list of view counts.

    Args:
        views: List of integer view counts.

    Returns:
        Integer median value.
    """
    if not views:
        return 0
    series = pd.Series(views)
    median_val = series.median()
    return int(round(median_val)) if not pd.isna(median_val) else 0


def detect_outliers(
    posts: List[Dict[str, Any]],
    multiplier: Optional[float] = None,
    historical_median: Optional[int] = None,
) -> Tuple[int, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Classify posts as viral outliers based on the median view count and a multiplier threshold.

    Args:
        posts: List of post dictionary objects (must include 'views' key).
        multiplier: Multiplier factor (e.g. 3.0 means >= 3x the median). Defaults to settings.outlier_multiplier.
        historical_median: Optional pre-existing median from database to incorporate.

    Returns:
        Tuple of:
            - computed_median (int)
            - outlier_posts (List[Dict[str, Any]])
            - all_processed_posts (List[Dict[str, Any]] with 'is_outlier' and 'median_ratio' flags added)
    """
    mult = multiplier or settings.outlier_multiplier

    if not posts:
        logger.warning("No posts provided for outlier detection.")
        return historical_median or 0, [], []

    # Extract views from posts
    views_list = [int(p.get("views", 0)) for p in posts]

    # Calculate median (using current batch, optionally weighting with historical)
    batch_median = calculate_median_views(views_list)
    effective_median = historical_median if (historical_median and historical_median > 0) else batch_median

    if effective_median <= 0:
        logger.warning("Effective median views is 0. Cannot compute outlier ratio meaningfully.")
        for p in posts:
            p["is_outlier"] = False
            p["median_ratio"] = 0.0
        return 0, [], posts

    threshold = effective_median * mult
    logger.info(
        f"Outlier Detection Threshold: Median={effective_median:,} views, "
        f"Multiplier={mult}x, Cutoff={int(threshold):,} views."
    )

    outliers: List[Dict[str, Any]] = []

    for p in posts:
        v = int(p.get("views", 0))
        ratio = round(v / effective_median, 2) if effective_median > 0 else 0.0
        is_out = bool(v >= threshold)
        
        p["is_outlier"] = is_out
        p["median_ratio"] = ratio

        if is_out:
            outliers.append(p)

    logger.info(f"Detected {len(outliers)} outliers out of {len(posts)} analyzed posts.")
    return effective_median, outliers, posts
