from typing import Any, List, Optional, Dict
from pydantic import BaseModel, Field
from src.schema.enums import SourceName

class SourcedValue(BaseModel):
    """Every extractable field carries its source provenance."""
    value: Any
    source: str
    url: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

class Conflict(BaseModel):
    field_name: str
    values: List[SourcedValue]

class UnitConfig(BaseModel):
    unit_type: str
    count: Optional[int] = None
    carpet_area_sqft: Optional[float] = None
    rate_per_sqft: Optional[SourcedValue] = None
    sale_value_crores: Optional[SourcedValue] = None

class CostLineItem(BaseModel):
    item: str
    total: float
    incurred: float
    balance: float

class FinanceLineItem(BaseModel):
    source: str
    total: float
    incurred: float
    balance: float

class BuildingStatus(BaseModel):
    building_name: str
    structure: str
    approval: str
    stage: str
    start_date: str
    end_date: str

class PartialBrief(BaseModel):
    """Data collected by a single agent."""
    source: str
    data: Dict[str, Any]

class ProjectBrief(BaseModel):
    """Complete output — maps 1:1 to the analyst's Word template."""
    
    # Row 1: Facility
    facility_crores: Optional[SourcedValue] = None
    
    # Row 2: Plot Area
    plot_area: Optional[SourcedValue] = None
    
    # Row 3: Group Name
    group_name: Optional[SourcedValue] = None
    
    # Row 4: Type
    project_type: Optional[SourcedValue] = None
    
    # Row 5: Location
    location: Optional[SourcedValue] = None
    
    # Row 6: Configuration
    configuration: Optional[SourcedValue] = None
    
    # Row 7: RERA
    rera_number: str
    rera_status: Optional[SourcedValue] = None
    rera_registration_date: Optional[SourcedValue] = None
    rera_validity_end: Optional[SourcedValue] = None
    
    # Row 8: Salient Features
    salient_features: Optional[str] = None
    developer_track_record: Optional[SourcedValue] = None
    years_in_business: Optional[SourcedValue] = None
    delivered_area: Optional[SourcedValue] = None
    group_net_worth: Optional[SourcedValue] = None
    other_business_lines: List[SourcedValue] = Field(default_factory=list)
    debt_exposure: Optional[SourcedValue] = None
    lender_name: Optional[SourcedValue] = None
    promoter_equity_pct: Optional[SourcedValue] = None
    balance_cost_crores: Optional[SourcedValue] = None
    total_receivables_crores: Optional[SourcedValue] = None
    location_advantage: Optional[List[Dict[str, Any]]] = None
    
    # Row 9: Construction & Approval Status
    buildings: List[BuildingStatus] = Field(default_factory=list)
    
    # Row 10: Project Numbers
    project_cost: List[CostLineItem] = Field(default_factory=list)
    means_of_finance: List[FinanceLineItem] = Field(default_factory=list)
    revenue_snapshot: List[UnitConfig] = Field(default_factory=list)
    
    # Metadata
    conflicts: List[Conflict] = Field(default_factory=list)
    sources_queried: Dict[str, str] = Field(default_factory=dict)
    extraction_timestamp: Optional[str] = None
    data_completeness_pct: float = 0.0
