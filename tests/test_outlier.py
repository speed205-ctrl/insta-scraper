"""
Unit tests for outlier detection and median calculations.
"""

from scrapper.outlier import calculate_median_views, detect_outliers


def test_calculate_median_views_empty():
    assert calculate_median_views([]) == 0


def test_calculate_median_views_odd():
    # Odd count: 1000, 2000, 3000 -> median is 2000
    views = [1000, 3000, 2000]
    assert calculate_median_views(views) == 2000


def test_calculate_median_views_even():
    # Even count: 1000, 2000, 3000, 4000 -> median is (2000 + 3000) / 2 = 2500
    views = [1000, 4000, 2000, 3000]
    assert calculate_median_views(views) == 2500


def test_detect_outliers_identifies_virals():
    # Baseline median is 10,000 views
    # Threshold at 3.0x is 30,000 views
    posts = [
        {"shortcode": "A1", "views": 8000},
        {"shortcode": "A2", "views": 10000},
        {"shortcode": "A3", "views": 12000},
        {"shortcode": "VIRAL1", "views": 35000},
        {"shortcode": "VIRAL2", "views": 150000},
    ]

    median, outliers, classified = detect_outliers(posts, multiplier=3.0)

    assert median == 12000
    # Threshold is 12000 * 3 = 36000
    assert len(outliers) == 1
    assert outliers[0]["shortcode"] == "VIRAL2"
    assert outliers[0]["is_outlier"] is True
    assert classified[0]["is_outlier"] is False


def test_detect_outliers_with_explicit_threshold():
    posts = [
        {"shortcode": "A1", "views": 5000},
        {"shortcode": "A2", "views": 5000},
        {"shortcode": "VIRAL", "views": 16000},
    ]
    # Median is 5000, threshold at 3.0x is 15000
    median, outliers, classified = detect_outliers(posts, multiplier=3.0)
    assert median == 5000
    assert len(outliers) == 1
    assert outliers[0]["shortcode"] == "VIRAL"
    assert outliers[0]["median_ratio"] == 3.2
