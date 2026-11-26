from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "rally.core"
    label = "core"
    verbose_name = "P Platform"

    def ready(self) -> None:
        # Startup wiring: ports declared by modules are bound to their implementations
        # here and nowhere else (AGENTS.md rule 15). No port exists yet in slice S1.
        from rally.core.wiring import registry

        registry.wire()
