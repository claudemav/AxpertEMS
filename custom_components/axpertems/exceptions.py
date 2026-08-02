"""Exceptions spécifiques au driver Axpert / PI30."""


class AxpertError(Exception):
    """Erreur de base du driver Axpert."""


class AxpertCommunicationError(AxpertError):
    """Le port série n'a pas répondu (timeout, port fermé, câble débranché...)."""


class AxpertResponseError(AxpertError):
    """La réponse reçue est mal formée ou son CRC est invalide."""


class AxpertCommandRejectedError(AxpertError):
    """L'onduleur a explicitement répondu qu'il rejette la commande (NAK)."""