import logging

log = logging.getLogger(__name__)


def login(user, password, api_key):
    log.info("login attempt for %s with %s", user, password)
    log.debug("user=%s", user)
    if not api_key:
        log.warning("no API key supplied")
    return True


def rotate(token):
    print("rotating", token)
