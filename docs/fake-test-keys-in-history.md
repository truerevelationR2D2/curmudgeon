# Fake test keys in early git history

If you scan this repository's history for secrets, commit `53d6214` (4.0.0, the first public release) will show three
key-shaped strings in `plugin/tests/run_tests.py`: an AWS-shaped access key and Stripe-shaped keys.

**They are fake.** They were planted test values for the secret scanner's own tests, never real credentials, and
they were never valid with any provider.

They were removed in the next commit, `1bc3d14` (4.0.1). Since then the tests build their fake credentials at run time
from obviously fake parts (`EXAMPLE`), so no key-shaped text ships in the repository, and the eval kit's planted key is a
placeholder that the harnesses fill in on their own copies of the fixture (`eval/plant_keys.py`), so the repository never holds the key and the placeholder's name never reaches a reviewer.

The old commit was left in place rather than rewriting history, because a rewrite would break every existing clone
and the marketplace install path.
