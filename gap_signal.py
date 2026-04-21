from __future__ import annotations

import json
from pydantic import BaseModel
import psycopg
from psycopg.types.json import Jsonb

class GapSignal(BaseModel):
    query: str
    topic_needed: str
    jurisdiction_needed: str
    gap_description: str
    metadata: dict = {}

def emit_gap_signal(signal: GapSignal, conn: psycopg.Connection) -> str:
    """
    Inserts a newly detected knowledge gap signal directly into the database.
    This provides the 'Pull Signal' for the curation dashboard.
    """
    sql = """
        INSERT INTO knowledge_gap_signals (
            query, 
            topic_needed, 
            jurisdiction_needed, 
            gap_description, 
            metadata
        ) VALUES (
            %(query)s, 
            %(topic_needed)s, 
            %(jurisdiction_needed)s, 
            %(gap_description)s, 
            %(metadata)s
        ) RETURNING id;
    """
    
    params = {
        "query": signal.query,
        "topic_needed": signal.topic_needed,
        "jurisdiction_needed": signal.jurisdiction_needed,
        "gap_description": signal.gap_description,
        "metadata": Jsonb(signal.metadata)
    }
    
    with conn.cursor() as cur:
        cur.execute(sql, params)
        inserted_id = cur.fetchone()[0]
        conn.commit()
        
    return str(inserted_id)
