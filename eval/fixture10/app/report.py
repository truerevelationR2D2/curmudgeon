import logging

logger = logging.getLogger("report")


def build(rows, token_count, password_policy):
    logger.info("built %d rows", len(rows))
    logger.info("token_count=%d", token_count)
    logger.info("password policy: %s", "min 12 characters")
    logger.info("has token: %s", bool(rows))
    return rows
