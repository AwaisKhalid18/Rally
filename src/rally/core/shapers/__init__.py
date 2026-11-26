"""Response shapers.

Every outbound payload is built here from an explicit public view model. A domain entity,
model instance or queryset is never serialised or handed to a template (AGENTS.md §5
Privacy, FE-1). Private fields cannot leak because they are not in the view models.
"""
