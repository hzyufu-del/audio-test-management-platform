class WorkflowServiceError(Exception):
    code = "internal_error"
    status_code = 500

    def __init__(self, message, details=None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class WorkflowNotFoundError(WorkflowServiceError):
    code = "not_found"
    status_code = 404


class WorkflowConflictError(WorkflowServiceError):
    code = "conflict"
    status_code = 409


class WorkflowPersistenceError(WorkflowServiceError):
    code = "internal_error"
    status_code = 500
