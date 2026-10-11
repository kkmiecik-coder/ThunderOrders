"""Wyjątek domenowy pupili — trasy (etap 4) mapują go na JSON {ok, error, message} i status."""


class PetError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
