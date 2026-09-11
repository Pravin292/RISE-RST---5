import re

from services.neo4j_service import neo4j_service

NO_INFO_ANSWER = "I don't have enough information in the uploaded data to answer this question."
NO_DATASET_ANSWER = "No dataset has been uploaded yet. I cannot answer this question."

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "of", "in", "on", "at", "by", "from", "to", "into", "as", "that",
    "which", "who", "whom", "this", "these", "those", "it", "its",
    "what", "how", "when", "where", "why", "does", "do", "did", "doing",
    "have", "has", "had", "having", "can", "could", "would", "should",
    "will", "shall", "may", "might", "must",
    "many", "much", "show", "me", "my", "list", "all", "any", "rows",
    "records", "entries", "belong", "belongs", "with", "value", "values",
    "please", "give", "row", "record", "there", "available", "unique",
    "and", "or", "not", "no", "yes", "about", "than", "then", "so",
    "some", "such", "each", "every", "per", "get", "tell", "find",
}


def _tokenize(question: str) -> list[str]:
    return re.findall(r"[a-z0-9_.']+", question.lower())


def _find_column(tokens: list[str], columns: list[str]) -> str | None:
    joined = " ".join(tokens)
    for col in columns:
        col_variants = {col, col.rstrip("s"), col + "s"}
        for variant in col_variants:
            if re.search(rf"\b{re.escape(variant)}\b", joined):
                return col
    # Fallback: match against individual parts of an underscore-joined column
    # name, e.g. a "topic_id" column matches a question that just says "topic".
    token_set = set(tokens)
    for col in columns:
        for part in col.split("_"):
            if len(part) <= 2:
                continue
            if {part, part.rstrip("s"), part + "s"} & token_set:
                return col
    return None


def _column_stats(dataset_id: str, col: str) -> dict:
    rec = neo4j_service.run_read(
        f"""
        MATCH (:Dataset {{id: $dataset_id}})-[:HAS_ROW]->(r:Row)
        WHERE r.`{col}` IS NOT NULL AND r.`{col}` <> ''
        RETURN count(r) AS total, count(DISTINCT r.`{col}`) AS distinct_count,
               avg(size(toString(r.`{col}`))) AS avg_len
        """,
        dataset_id=dataset_id,
    )
    return rec[0] if rec else {"total": 0, "distinct_count": 0, "avg_len": 0}


def _is_categorical(stats: dict) -> bool:
    total = stats.get("total") or 0
    distinct = stats.get("distinct_count") or 0
    avg_len = stats.get("avg_len") or 0
    if total == 0:
        return False
    if avg_len and avg_len > 40:
        return False
    return distinct <= max(25, total * 0.5)


def _find_value(tokens: list[str], columns: list[str], dataset_id: str) -> tuple[str, str] | None:
    """Try to find (column, value) where the question refers to a distinct value
    of some categorical column in the dataset. Free-text columns (long strings,
    near-unique values like ids or narrative text) are skipped so common English
    words in the question can't accidentally match inside them."""
    candidates = [t for t in tokens if t not in STOPWORDS and not t.isdigit()]
    if not candidates:
        return None
    phrase = " ".join(candidates)

    categorical_cols = [c for c in columns if _is_categorical(_column_stats(dataset_id, c))]

    value_maps: dict[str, dict[str, str]] = {}
    for col in categorical_cols:
        rows = neo4j_service.run_read(
            f"""
            MATCH (:Dataset {{id: $dataset_id}})-[:HAS_ROW]->(r:Row) WHERE r.`{col}` IS NOT NULL
            RETURN DISTINCT toLower(r.`{col}`) AS v, r.`{col}` AS orig
            LIMIT 500
            """,
            dataset_id=dataset_id,
        )
        value_maps[col] = {row["v"]: row["orig"] for row in rows}

    # Phase 1: exact match of the full candidate phrase, or any single candidate token.
    for col in categorical_cols:
        vmap = value_maps[col]
        if phrase in vmap:
            return col, vmap[phrase]
        for cand in candidates:
            if cand in vmap:
                return col, vmap[cand]

    # Phase 2: whole-word fuzzy match, categorical columns only.
    for col in categorical_cols:
        vmap = value_maps[col]
        for cand in candidates:
            for v, orig in vmap.items():
                if cand in v.split():
                    return col, orig
    return None


def answer_question(question: str, dataset_id: str | None) -> dict:
    if not dataset_id or not neo4j_service.dataset_exists(dataset_id):
        return {"answer": NO_DATASET_ANSWER, "cypher": "", "result": [], "grounded": False}

    columns = neo4j_service.get_columns(dataset_id)
    tokens = _tokenize(question)
    q = question.lower()

    base_match = "MATCH (d:Dataset {id: $dataset_id})-[:HAS_ROW]->(r:Row)"

    # 0. Column / schema questions ("how many columns", "what columns/fields are there")
    if re.search(r"\bcolumns?\b", q) or re.search(r"\bfields?\b", q):
        cypher = "MATCH (d:Dataset {id: $dataset_id}) RETURN d.columns AS columns"
        result = neo4j_service.run_read(cypher, dataset_id=dataset_id)
        cols = result[0]["columns"] if result else []
        if re.search(r"\bhow many\b", q):
            answer = f"There are {len(cols)} columns: {', '.join(cols)}."
        else:
            answer = f"The columns are: {', '.join(cols)}."
        return {"answer": answer, "cypher": cypher, "result": result, "grounded": True}

    # 1. Aggregation: average / sum
    agg_match = re.search(r"\b(average|avg|mean|sum|total)\b", q)
    if agg_match:
        col = _find_column(tokens, columns)
        if col:
            func = "avg" if agg_match.group(1) in ("average", "avg", "mean") else "sum"
            cypher = f"{base_match} RETURN {func}(toFloat(r.`{col}`)) AS {func}_{col}"
            try:
                result = neo4j_service.run_read(cypher, dataset_id=dataset_id)
            except Exception:
                result = []
            value = result[0][f"{func}_{col}"] if result else None
            if value is None:
                return {"answer": NO_INFO_ANSWER, "cypher": cypher, "result": [], "grounded": False}
            value = round(value, 2)
            verb = "average" if func == "avg" else "sum"
            return {
                "answer": f"The {verb} of {col} is {value}.",
                "cypher": cypher,
                "result": result,
                "grounded": True,
            }

    # 2. Min / Max
    minmax_match = re.search(r"\b(maximum|max|highest|largest|minimum|min|lowest|smallest)\b", q)
    if minmax_match:
        col = _find_column(tokens, columns)
        if col:
            is_max = minmax_match.group(1) in ("maximum", "max", "highest", "largest")
            func = "max" if is_max else "min"
            cypher = f"{base_match} RETURN {func}(toFloat(r.`{col}`)) AS {func}_{col}"
            try:
                result = neo4j_service.run_read(cypher, dataset_id=dataset_id)
            except Exception:
                result = []
            value = result[0][f"{func}_{col}"] if result else None
            if value is None:
                return {"answer": NO_INFO_ANSWER, "cypher": cypher, "result": [], "grounded": False}
            label = "maximum" if is_max else "minimum"
            return {
                "answer": f"The {label} {col} is {value}.",
                "cypher": cypher,
                "result": result,
                "grounded": True,
            }

    # 3. List unique values of a column
    if re.search(r"\b(unique|distinct|what .* available|what .* exist|which .* exist|list)\b", q):
        col = _find_column(tokens, columns)
        if col:
            cypher = f"{base_match} RETURN DISTINCT r.`{col}` AS value ORDER BY value"
            result = neo4j_service.run_read(cypher, dataset_id=dataset_id)
            if not result:
                return {"answer": NO_INFO_ANSWER, "cypher": cypher, "result": [], "grounded": False}
            values = [str(r["value"]) for r in result if r["value"] not in (None, "")]
            return {
                "answer": f"The unique values of {col} are: {', '.join(values)}.",
                "cypher": cypher,
                "result": result,
                "grounded": True,
            }

    is_count_query = re.search(
        r"\b(how many|count|number of|total number|row count|rows? ?count|total rows)\b", q
    ) is not None
    wants_show = re.search(r"\b(show|display|list|give me)\b", q) is not None

    value_match = _find_value(tokens, columns, dataset_id)

    # 4. Show matching rows for a specific value (explicit "show"/"display"/"list ... rows")
    if value_match and wants_show and not is_count_query:
        col, val = value_match
        cypher = f"{base_match} WHERE r.`{col}` = $val RETURN properties(r) AS row LIMIT 10"
        result = neo4j_service.run_read(cypher, dataset_id=dataset_id, val=val)
        if not result:
            return {"answer": NO_INFO_ANSWER, "cypher": cypher, "result": [], "grounded": False}
        return {
            "answer": f"Found {len(result)} row(s) where {col} = '{val}' (showing up to 10).",
            "cypher": cypher,
            "result": result,
            "grounded": True,
        }

    # 5. Count rows matching a value ("how many/count/number of ... <value>", or
    # a bare value-bearing question like "negative sentiment count")
    if value_match and (is_count_query or not wants_show):
        col, val = value_match
        cypher = f"{base_match} WHERE r.`{col}` = $val RETURN count(r) AS count"
        result = neo4j_service.run_read(cypher, dataset_id=dataset_id, val=val)
        count = result[0]["count"] if result else 0
        return {
            "answer": f"There are {count} rows where {col} = '{val}'.",
            "cypher": cypher,
            "result": result,
            "grounded": True,
        }

    # 6. Count all rows ("how many rows", "count rows", "row count", "total rows", ...)
    if is_count_query:
        cypher = f"{base_match} RETURN count(r) AS count"
        result = neo4j_service.run_read(cypher, dataset_id=dataset_id)
        count = result[0]["count"] if result else 0
        return {
            "answer": f"There are {count} rows in total.",
            "cypher": cypher,
            "result": result,
            "grounded": True,
        }

    # 7. Describe / summarize the dataset
    if re.search(r"\b(describe|summary|summarize|overview)\b", q):
        cypher = f"{base_match} RETURN count(r) AS rows"
        result = neo4j_service.run_read(cypher, dataset_id=dataset_id)
        rows = result[0]["rows"] if result else 0
        answer = (
            f"This dataset has {rows} rows and {len(columns)} columns: "
            f"{', '.join(columns)}."
        )
        return {"answer": answer, "cypher": cypher, "result": result, "grounded": True}

    return {"answer": NO_INFO_ANSWER, "cypher": "", "result": [], "grounded": False}
