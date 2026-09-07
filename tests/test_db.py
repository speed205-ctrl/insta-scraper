"""
Unit tests for Database models and operations with in-memory SQLite.
"""

from datetime import datetime, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from scrapper.db import Base, Competitor, Reel, AIAnalysis, ScrapeRun


def test_database_models_in_memory():
    # Use SQLite in-memory for isolated testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # 1. Create Competitor
    competitor = Competitor(username="testcompetitor", median_views=15000)
    session.add(competitor)
    session.commit()

    assert competitor.id is not None
    assert competitor.username == "testcompetitor"

    # 2. Create ScrapeRun
    run = ScrapeRun(
        competitor_id=competitor.id,
        status="completed",
        posts_fetched=20,
        outliers_found=2,
    )
    session.add(run)
    session.commit()

    assert run.id is not None
    assert run.competitor.username == "testcompetitor"

    # 3. Create Reel
    reel = Reel(
        competitor_id=competitor.id,
        shortcode="TEST1234",
        url="https://www.instagram.com/p/TEST1234/",
        views=60000,
        likes=3500,
        comments=200,
        shares=150,
        duration_secs=32.5,
        is_outlier=True,
        published_at=datetime.now(timezone.utc),
    )
    session.add(reel)
    session.commit()

    assert reel.id is not None
    assert reel.is_outlier is True
    assert round(reel.engagement_rate, 4) > 0

    # 4. Create AIAnalysis
    analysis = AIAnalysis(
        reel_id=reel.id,
        transcript="Texto transcrito de prueba",
        hook_text="¿Sabías esto?",
        hook_type="Pregunta",
        hook_score=9,
        psychological_trigger="Curiosidad extrema",
        generated_script="[GANCHO] Nuevo guion",
        model_used="gemini-2.5-flash",
        prompt_version="v1.0",
    )
    session.add(analysis)
    session.commit()

    # 5. Query and Assert relationships
    stmt = select(Reel).where(Reel.shortcode == "TEST1234")
    fetched_reel = session.scalars(stmt).first()
    assert fetched_reel is not None
    assert fetched_reel.analysis is not None
    assert fetched_reel.analysis.hook_score == 9
    assert fetched_reel.competitor.username == "testcompetitor"

    session.close()
