from django.apps import AppConfig


class PlayerCollectionsConfig(AppConfig):
    # The logical module name is `collections`, which is a Python standard-library
    # module; a top-level package of that name would shadow it (AGENTS.md section 3.1).
    name = "rally.modules.player_collections"
    label = "player_collections"
    verbose_name = "M8 Player Collections"
