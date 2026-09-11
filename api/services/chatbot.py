import re
import logging
from typing import Dict, Any, List, Optional
from services.neo4j_service import neo4j_service

logger = logging.getLogger("chatbot_service")
logging.basicConfig(level=logging.INFO)

# Column Aliases
COLUMN_ALIASES = {
    "dept": "department",
    "division": "department",
    "location": "city",
    "town": "city",
    "pay": "salary",
    "income": "salary",
    "earnings": "salary",
    "years": "age"
}

class RuleBasedChatbot:
    def __init__(self):
        pass

    def _normalize_text(self, text: str) -> str:
        return text.strip().lower()

    def _find_matching_property(self, question: str, available_props: List[str]) -> Optional[str]:
        q_norm = self._normalize_text(question)
        words = re.findall(r'\b\w+\b', q_norm)
        
        # Check direct prop match
        for prop in available_props:
            if prop.lower() in words or prop.lower() in q_norm:
                return prop
                
        # Check alias match
        for alias, target in COLUMN_ALIASES.items():
            if alias in words or alias in q_norm:
                if target in available_props:
                    return target
                    
        return None

    def process_question(self, question: str) -> Dict[str, Any]:
        q_norm = self._normalize_text(question)
        
        # 1. Check if graph has any data
        total_rows = neo4j_service.get_active_row_count()
        if total_rows == 0:
            return {
                "answer": "No dataset is currently loaded. Please upload a CSV first.",
                "cypher": None,
                "result": [],
                "grounded": False
            }

        available_props = neo4j_service.get_active_row_properties()
        logger.info(f"Available properties in graph: {available_props}")

        # -------------------------------------------------------------
        # INTENT 1: UNFILTERED COUNT ALL (e.g., "How many rows are there?")
        # -------------------------------------------------------------
        if re.search(r'\b(how many (rows|records|data|entries|total)|total (rows|records|count)|count (rows|records|all))\b', q_norm):
            has_filter_keyword = bool(re.search(r'\b(in|where|from|with|for|having)\b', q_norm))
            if not has_filter_keyword:
                cypher = "MATCH (r:Row) RETURN count(r) AS count"
                res = neo4j_service.execute_cypher(cypher)
                count = res[0]["count"] if res else 0
                return {
                    "answer": f"There are {count} total rows in the dataset.",
                    "cypher": cypher,
                    "result": res,
                    "grounded": True
                }

        # -------------------------------------------------------------
        # INTENT 3: UNIQUE VALUES (e.g., "What are the unique departments?")
        # -------------------------------------------------------------
        if re.search(r'\b(unique|distinct|list|what are|show)\b', q_norm) and any(kw in q_norm for kw in ["unique", "distinct", "what are"]):
            prop = self._find_matching_property(q_norm, available_props)
            if prop:
                cypher = f"MATCH (r:Row) WHERE r.{prop} IS NOT NULL RETURN DISTINCT r.{prop} AS value ORDER BY value"
                res = neo4j_service.execute_cypher(cypher)
                vals = [str(r.get("value", r.get("val"))) for r in res if r.get("value") is not None or r.get("val") is not None]
                if vals:
                    val_str = ", ".join(vals)
                    return {
                        "answer": f"The unique values for '{prop}' are: {val_str}.",
                        "cypher": cypher,
                        "result": res,
                        "grounded": True
                    }

        # -------------------------------------------------------------
        # INTENT 5 & 6 & 7: AGGREGATIONS (AVG, MIN, MAX, SUM)
        # -------------------------------------------------------------
        # Average
        if re.search(r'\b(average|mean|avg)\b', q_norm):
            prop = self._find_matching_property(q_norm, available_props)
            if prop:
                cypher = f"MATCH (r:Row) WHERE r.{prop} IS NOT NULL RETURN avg(toFloat(r.{prop})) AS average"
                res = neo4j_service.execute_cypher(cypher)
                avg_val = res[0]["average"] if res and res[0]["average"] is not None else None
                if avg_val is not None:
                    return {
                        "answer": f"The average {prop} is {round(avg_val, 2)}.",
                        "cypher": cypher,
                        "result": res,
                        "grounded": True
                    }

        # Max / Maximum / Highest
        if re.search(r'\b(max|maximum|highest|top|most)\b', q_norm):
            prop = self._find_matching_property(q_norm, available_props)
            if prop:
                cypher = f"MATCH (r:Row) WHERE r.{prop} IS NOT NULL RETURN max(toFloat(r.{prop})) AS max_val"
                res = neo4j_service.execute_cypher(cypher)
                max_val = res[0]["max_val"] if res and res[0]["max_val"] is not None else None
                if max_val is not None:
                    return {
                        "answer": f"The maximum {prop} is {max_val}.",
                        "cypher": cypher,
                        "result": res,
                        "grounded": True
                    }

        # Min / Minimum / Lowest
        if re.search(r'\b(min|minimum|lowest|bottom|least)\b', q_norm):
            prop = self._find_matching_property(q_norm, available_props)
            if prop:
                cypher = f"MATCH (r:Row) WHERE r.{prop} IS NOT NULL RETURN min(toFloat(r.{prop})) AS min_val"
                res = neo4j_service.execute_cypher(cypher)
                min_val = res[0]["min_val"] if res and res[0]["min_val"] is not None else None
                if min_val is not None:
                    return {
                        "answer": f"The minimum {prop} is {min_val}.",
                        "cypher": cypher,
                        "result": res,
                        "grounded": True
                    }

        # Sum / Total
        if re.search(r'\b(sum|total sum|overall)\b', q_norm) and not re.search(r'\b(total rows|total records)\b', q_norm):
            prop = self._find_matching_property(q_norm, available_props)
            if prop:
                cypher = f"MATCH (r:Row) WHERE r.{prop} IS NOT NULL RETURN sum(toFloat(r.{prop})) AS total"
                res = neo4j_service.execute_cypher(cypher)
                total_val = res[0]["total"] if res and res[0]["total"] is not None else None
                if total_val is not None:
                    return {
                        "answer": f"The total sum of {prop} is {round(total_val, 2)}.",
                        "cypher": cypher,
                        "result": res,
                        "grounded": True
                    }

        # -------------------------------------------------------------
        # INTENT 2 & 4: COUNT WITH FILTER / SHOW ROWS
        # -------------------------------------------------------------
        # Scan all available properties to find property value matching the question
        for prop in available_props:
            try:
                distinct_cypher = f"MATCH (r:Row) WHERE r.{prop} IS NOT NULL RETURN DISTINCT r.{prop} AS val"
                records = neo4j_service.execute_cypher(distinct_cypher)
                for rec in records:
                    val = str(rec.get("val", rec.get("value", "")))
                    val_norm = val.lower()
                    if val_norm and val_norm in q_norm:
                        is_count = bool(re.search(r'\b(how many|count|number of)\b', q_norm))
                        if is_count:
                            cypher = f"MATCH (r:Row) WHERE toLower(toString(r.{prop})) = toLower('{val}') RETURN count(r) AS count"
                            res = neo4j_service.execute_cypher(cypher)
                            c = res[0]["count"] if res else 0
                            return {
                                "answer": f"There are {c} rows where {prop} = '{val}'.",
                                "cypher": cypher,
                                "result": res,
                                "grounded": True
                            }
                        else:
                            cypher = f"MATCH (r:Row) WHERE toLower(toString(r.{prop})) = toLower('{val}') RETURN r LIMIT 10"
                            res = neo4j_service.execute_cypher(cypher)
                            count = len(res)
                            return {
                                "answer": f"Found {count} matching record(s) where {prop} = '{val}' (showing top 10).",
                                "cypher": cypher,
                                "result": [r["r"] for r in res if "r" in r],
                                "grounded": True
                            }
            except Exception as e:
                logger.error(f"Error scanning values for prop {prop}: {e}")

        # Generic count fallback ("how many rows...")
        if "how many" in q_norm or "count" in q_norm or "rows" in q_norm or "total" in q_norm:
            cypher = "MATCH (r:Row) RETURN count(r) AS count"
            res = neo4j_service.execute_cypher(cypher)
            count = res[0]["count"] if res else 0
            return {
                "answer": f"There are {count} total rows in the dataset.",
                "cypher": cypher,
                "result": res,
                "grounded": True
            }

        # -------------------------------------------------------------
        # FALLBACK / UNSUPPORTED QUESTION
        # -------------------------------------------------------------
        return {
            "answer": "I couldn't answer that question from the available dataset.",
            "cypher": None,
            "result": [],
            "grounded": False
        }

chatbot_engine = RuleBasedChatbot()
