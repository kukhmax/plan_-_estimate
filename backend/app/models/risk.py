import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.checklist import Substrate


class RiskSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskConditionOperator(str, enum.Enum):
    FINDING_PRESENT = "FINDING_PRESENT"
    FINDING_ABSENT = "FINDING_ABSENT"
    NUMBER_AT_LEAST = "NUMBER_AT_LEAST"
    NUMBER_AT_MOST = "NUMBER_AT_MOST"
    SUBSTRATE_IN = "SUBSTRATE_IN"
    SUBSTRATE_NOT_IN = "SUBSTRATE_NOT_IN"
    TARGET_IN = "TARGET_IN"
    QUALITY_IN = "QUALITY_IN"


class RiskRule(Base):
    __tablename__ = "risk_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    severity: Mapped[RiskSeverity] = mapped_column(
        Enum(RiskSeverity, name="riskseverity"),
        nullable=False,
    )
    blocks_finishing: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Risk that must be remediated before finishing work can start",
    )
    warranty_exclusion_candidate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Risk eligible to feed a formal contractor warranty disclaimer",
    )
    substrate: Mapped[Substrate | None] = mapped_column(
        Enum(Substrate, name="substrate"),
        nullable=True,
        comment="Restricts the rule to one substrate (null = applies to all)",
    )
    title_key: Mapped[str] = mapped_column(String(255), nullable=False)
    explanation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    consequence_key: Mapped[str] = mapped_column(String(255), nullable=False)
    mitigation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    communication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_risk_rules_code_version"),
    )


class RiskRuleCondition(Base):
    __tablename__ = "risk_rule_conditions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("risk_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    operator: Mapped[RiskConditionOperator] = mapped_column(
        Enum(RiskConditionOperator, name="riskconditionoperator"),
        nullable=False,
    )
    finding_key: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment="Finding key the operator tests (null for substrate/target/quality ops)",
    )
    value_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            '{"value": "3.000"} numeric threshold, or {"values": [...]} for '
            "SUBSTRATE/TARGET/QUALITY membership operators"
        ),
    )

    __table_args__ = (
        Index("ix_risk_rule_conditions_rule_position", "rule_id", "position"),
    )


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("inspections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    risk_code: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Stable machine-readable key consumed by downstream stages",
    )
    rule_code: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Code of the rule that produced this risk",
    )
    rule_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Rule version evaluated at materialization time",
    )
    severity: Mapped[RiskSeverity] = mapped_column(
        Enum(RiskSeverity, name="riskseverity"),
        nullable=False,
    )
    title_key: Mapped[str] = mapped_column(String(255), nullable=False)
    explanation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    consequence_key: Mapped[str] = mapped_column(String(255), nullable=False)
    mitigation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    communication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    warranty_exclusion_candidate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    blocks_finishing: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    source_signature: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "SHA-256 over sorted source finding UUIDs; part of the stable "
            "identity so the risk row survives finding churn"
        ),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the risk stopped being confirmed by the latest evaluation",
    )
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "inspection_id",
            "rule_code",
            "source_signature",
            name="uq_risks_inspection_rule_signature",
        ),
        Index("ix_risks_inspection_active", "inspection_id", "is_active"),
        Index("ix_risks_room_active", "room_id", "is_active"),
    )


class RiskFinding(Base):
    __tablename__ = "risk_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    risk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("inspection_findings.id", ondelete="SET NULL"),
        nullable=True,
        comment="Source inspection finding (nullable so the snapshot survives)",
    )
    finding_key_snapshot: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Source finding key captured at materialization time",
    )
    value_snapshot: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Source finding value snapshot captured at materialization time",
    )
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "risk_id",
            "finding_id",
            name="uq_risk_findings_risk_finding",
        ),
        Index("ix_risk_findings_risk_position", "risk_id", "position"),
    )
