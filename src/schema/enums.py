from enum import Enum

class SourceName(str, Enum):
    MAHARERA = "maharera"
    NINETY_NINE_ACRES = "99acres"
    HOUSING_COM = "housing.com"
    ZAUBACORP = "zaubacorp"
    DEVELOPER_SITE = "developer"
    AUTODCR = "autodcr"
    USER_INPUT = "user_input"

class ProjectType(str, Enum):
    REDEVELOPMENT = "Redevelopment"
    NEW_PROJECT = "New Project"
    UNKNOWN = "Unknown"
