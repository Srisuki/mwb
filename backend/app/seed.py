from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    AuditArea,
    AuditPlan,
    ChecklistItem,
    Entity,
    ManagementReply,
    Observation,
    ObservationHistory,
    ObservationStatus,
    Organization,
    Permission,
    PlanStatus,
    Report,
    ReportStatus,
    RiskLevel,
    Role,
    User,
)
from app.services.legacy_baseline import seed_legacy_baseline

PERMISSIONS = [
    "VIEW_DASHBOARD",
    "VIEW_AUDIT_PLAN",
    "CREATE_AUDIT_PLAN",
    "EDIT_AUDIT_PLAN",
    "VIEW_AUDIT_ENTRY",
    "CREATE_OBSERVATION",
    "EDIT_OBSERVATION",
    "VIEW_CLIENT_REPLY",
    "CREATE_CLIENT_REPLY",
    "VIEW_REPORT",
    "GENERATE_REPORT",
    "APPROVE_REPORT",
    "LOCK_REPORT",
    "UPLOAD_DOCUMENT",
    "VIEW_DOCUMENT",
    "DOWNLOAD_DOCUMENT",
    "MANAGE_USERS",
    "MANAGE_CLIENTS",
    "MANAGE_ENTITIES",
    "MANAGE_AUDIT_AREAS",
    "MANAGE_CHECKLISTS",
    "MANAGE_SETTINGS",
    "USER_VIEW",
    "USER_CREATE",
    "USER_EDIT",
    "USER_ACTIVATE",
    "USER_DEACTIVATE",
    "ROLE_VIEW",
    "ROLE_MANAGE",
    "CLIENT_VIEW",
    "CLIENT_MANAGE",
    "AUDIT_PLAN_VIEW",
    "AUDIT_PLAN_CREATE",
    "AUDIT_PLAN_EDIT",
    "AUDIT_PLAN_ASSIGN",
    "AUDIT_EXECUTE",
    "OBSERVATION_VIEW",
    "OBSERVATION_CREATE",
    "OBSERVATION_EDIT",
    "MANAGEMENT_RESPONSE_VIEW",
    "MANAGEMENT_RESPONSE_CREATE",
    "REPORT_VIEW",
    "REPORT_GENERATE",
    "REPORT_APPROVE",
    "REPORT_LOCK",
    "DOCUMENT_VIEW",
    "DOCUMENT_UPLOAD",
    "AUDIT_HISTORY_VIEW",
    "SYSTEM_SETTINGS_MANAGE",
]
ROLE_PERMISSIONS = {
    "Admin / Partner": PERMISSIONS,
    "Audit Manager": [
        p
        for p in PERMISSIONS
        if p
        not in {
            "MANAGE_USERS",
            "MANAGE_CLIENTS",
            "USER_VIEW",
            "USER_CREATE",
            "USER_EDIT",
            "USER_ACTIVATE",
            "USER_DEACTIVATE",
            "ROLE_VIEW",
            "ROLE_MANAGE",
            "CLIENT_MANAGE",
        }
    ],
    "Audit Staff": [
        "VIEW_DASHBOARD",
        "VIEW_AUDIT_PLAN",
        "VIEW_AUDIT_ENTRY",
        "CREATE_OBSERVATION",
        "EDIT_OBSERVATION",
        "VIEW_REPORT",
        "GENERATE_REPORT",
        "UPLOAD_DOCUMENT",
        "VIEW_DOCUMENT",
        "DOWNLOAD_DOCUMENT",
        "AUDIT_PLAN_VIEW",
        "AUDIT_EXECUTE",
        "OBSERVATION_VIEW",
        "OBSERVATION_CREATE",
        "OBSERVATION_EDIT",
        "MANAGEMENT_RESPONSE_VIEW",
        "REPORT_VIEW",
        "REPORT_GENERATE",
        "DOCUMENT_VIEW",
        "DOCUMENT_UPLOAD",
    ],
    "Client Management": [
        "VIEW_DASHBOARD",
        "VIEW_AUDIT_ENTRY",
        "VIEW_CLIENT_REPLY",
        "CREATE_CLIENT_REPLY",
        "VIEW_REPORT",
        "VIEW_DOCUMENT",
        "DOWNLOAD_DOCUMENT",
        "UPLOAD_DOCUMENT",
        "CLIENT_VIEW",
        "OBSERVATION_VIEW",
        "MANAGEMENT_RESPONSE_VIEW",
        "MANAGEMENT_RESPONSE_CREATE",
        "REPORT_VIEW",
        "DOCUMENT_VIEW",
        "DOCUMENT_UPLOAD",
    ],
}


def seed_access(db):
    permissions = {}
    for code in PERMISSIONS:
        item = db.scalar(select(Permission).where(Permission.code == code)) or Permission(code=code)
        item.description = code.replace("_", " ").title()
        db.add(item)
        permissions[code] = item
    db.flush()
    for name, codes in ROLE_PERMISSIONS.items():
        role = db.scalar(select(Role).where(Role.name == name)) or Role(name=name)
        role.code = {
            "Admin / Partner": "ADMIN_PARTNER",
            "Audit Manager": "AUDIT_MANAGER",
            "Audit Staff": "AUDIT_STAFF",
            "Client Management": "CLIENT_MANAGEMENT",
        }[name]
        role.description = {
            "Admin / Partner": "Full administration and audit authority",
            "Audit Manager": "Plans, assigns, reviews, reports, and views audit history",
            "Audit Staff": "Executes assigned audits and maintains observations and evidence",
            "Client Management": "Responds to observations within assigned client scope",
        }[name]
        role.is_system_role = True
        role.is_active = True
        role.permissions = [permissions[code] for code in codes]
        db.add(role)
    db.commit()


SAMPLE_AREAS = {
    "Sales Audit": [
        "Whether GSTR-1 generated from Tally is free from all errors",
        "Whether taxable amount reflected in GSTR-1 matches with Profit & Loss Account",
        "Whether all item HSN are taxed at correct GST rates",
    ],
    "Bank Account Audit": [
        "BRS prepared periodically for all bank accounts",
        "Unreconciled entries identified, investigated and resolved timely",
        "Identification of unusual banking transactions",
    ],
    "Expenses Audit": [
        "Expenses supported with invoices/documents on test check basis",
        "Identification of personal nature expenses in P&L",
        "Analytical review of monthly variances",
    ],
}


def seed_sample_data(db, organization: Organization, admin: User) -> dict[str, int]:
    entities = {}
    for name, code in [
        ("Murali Industries", "MI"),
        ("W B Trading House", "WBTH"),
        ("MWB Technologies India Pvt. Ltd", "MWBT"),
    ]:
        entity = db.scalar(
            select(Entity).where(Entity.organization_id == organization.id, Entity.name == name)
        )
        if not entity:
            entity = Entity(organization_id=organization.id, name=name, code=code)
            db.add(entity)
            db.flush()
        entities[name] = entity

    areas = {}
    items = {}
    for area_order, (area_name, questions) in enumerate(SAMPLE_AREAS.items(), start=1):
        area = db.scalar(
            select(AuditArea).where(
                AuditArea.organization_id == organization.id, AuditArea.name == area_name
            )
        )
        if not area:
            area = AuditArea(organization_id=organization.id, name=area_name, sort_order=area_order)
            db.add(area)
            db.flush()
        areas[area_name] = area
        for item_order, question in enumerate(questions, start=1):
            item = db.scalar(
                select(ChecklistItem).where(
                    ChecklistItem.audit_area_id == area.id, ChecklistItem.question == question
                )
            )
            if not item:
                item = ChecklistItem(
                    audit_area_id=area.id,
                    question=question,
                    is_mandatory=True,
                    sort_order=item_order,
                )
                db.add(item)
                db.flush()
            items[(area_name, question)] = item

    current_period = date.today().strftime("%Y-%m")
    primary_entity = entities["Murali Industries"]
    plans = []
    for offset, area in enumerate(areas.values(), start=1):
        plan = db.scalar(
            select(AuditPlan).where(
                AuditPlan.entity_id == primary_entity.id,
                AuditPlan.period == current_period,
                AuditPlan.audit_area_id == area.id,
            )
        )
        if not plan:
            plan = AuditPlan(
                organization_id=organization.id,
                entity_id=primary_entity.id,
                audit_area_id=area.id,
                period=current_period,
                due_date=date.today() + timedelta(days=offset * 3),
                status=PlanStatus.IN_PROGRESS if offset == 1 else PlanStatus.PENDING,
                created_by_id=admin.id,
            )
            db.add(plan)
            db.flush()
        plans.append(plan)

    examples = [
        (
            "Sales Audit",
            SAMPLE_AREAS["Sales Audit"][0],
            RiskLevel.LOW,
            ObservationStatus.CLOSED,
            "GSTR-1 was generated and test checked; no errors were identified.",
            "Monthly control is operating effectively.",
        ),
        (
            "Sales Audit",
            SAMPLE_AREAS["Sales Audit"][1],
            RiskLevel.HIGH,
            ObservationStatus.MANAGEMENT_RESPONDED,
            "Sales as per GSTR-1 exceeds the ledger total by ₹48,250 for the month.",
            "Complete the reconciliation before the next return filing.",
        ),
        (
            "Bank Account Audit",
            SAMPLE_AREAS["Bank Account Audit"][0],
            RiskLevel.MEDIUM,
            ObservationStatus.PENDING,
            "The reconciliation for one current account was not available at the audit date.",
            "Prepare and review the reconciliation within seven days.",
        ),
        (
            "Expenses Audit",
            SAMPLE_AREAS["Expenses Audit"][0],
            RiskLevel.CRITICAL,
            ObservationStatus.REPEATED,
            "Three sampled expense entries totalling ₹1,26,400 lacked supporting invoices.",
            "Obtain evidence and introduce a payment-document control.",
        ),
    ]
    observations = []
    for area_name, question, risk, status_value, text, remark in examples:
        item = items[(area_name, question)]
        observation = db.scalar(
            select(Observation).where(
                Observation.entity_id == primary_entity.id,
                Observation.period == current_period,
                Observation.checklist_item_id == item.id,
            )
        )
        if not observation:
            area = areas[area_name]
            plan = next(plan for plan in plans if plan.audit_area_id == area.id)
            observation = Observation(
                organization_id=organization.id,
                entity_id=primary_entity.id,
                audit_plan_id=plan.id,
                audit_area_id=area.id,
                checklist_item_id=item.id,
                period=current_period,
                risk=risk,
                status=status_value,
                observation=text,
                remark=remark,
                responsible_person="Finance Manager",
                due_date=date.today() + timedelta(days=10),
                created_by_id=admin.id,
                updated_by_id=admin.id,
            )
            db.add(observation)
            db.flush()
            db.add(
                ObservationHistory(
                    observation_id=observation.id,
                    changed_by_id=admin.id,
                    action="SAMPLE_CREATED",
                    new_value={"status": status_value.value, "risk": risk.value},
                )
            )
        observations.append(observation)

    replied = next(
        item for item in observations if item.status == ObservationStatus.MANAGEMENT_RESPONDED
    )
    reply = db.scalar(select(ManagementReply).where(ManagementReply.observation_id == replied.id))
    if not reply:
        db.add(
            ManagementReply(
                observation_id=replied.id,
                comment="The difference relates to a credit note posted after the return extract.",
                action_taken="The ledger was corrected and a monthly reconciliation was assigned.",
                submitted_by_id=admin.id,
            )
        )

    report = db.scalar(
        select(Report).where(
            Report.entity_id == primary_entity.id,
            Report.period == current_period,
            Report.report_type == "Monthly Internal Audit Report",
        )
    )
    if not report:
        db.add(
            Report(
                organization_id=organization.id,
                entity_id=primary_entity.id,
                period=current_period,
                report_type="Monthly Internal Audit Report",
                status=ReportStatus.GENERATED,
                snapshot={
                    "sample": True,
                    "note": "Generated sample report; intentionally not approved or locked.",
                },
                generated_by_id=admin.id,
            )
        )
    db.commit()
    return {
        "entities": len(entities),
        "areas": len(areas),
        "checklist_items": len(items),
        "plans": len(plans),
        "observations": len(observations),
        "management_replies": 1,
        "reports": 1,
    }


def create_admin(
    email: str,
    password: str,
    full_name: str,
    organization_name: str,
    sample_data: bool = False,
    baseline_path: str | None = None,
):
    with SessionLocal() as db:
        seed_access(db)
        org = db.scalar(select(Organization).where(Organization.name == organization_name))
        if not org:
            org = Organization(name=organization_name, slug="mwb-group")
            db.add(org)
            db.flush()
        role = db.scalar(select(Role).where(Role.name == "Admin / Partner"))
        user = db.scalar(select(User).where(User.email == email.lower()))
        if not user:
            user = User(
                organization_id=org.id,
                role_id=role.id,
                email=email.lower(),
                full_name=full_name,
                password_hash=hash_password(password),
                must_change_password=True,
                is_verified=True,
            )
            db.add(user)
            db.flush()
            user.roles = [role]
            user.created_by_id = user.id
            user.updated_by_id = user.id
            user_result = "created"
        else:
            if user.organization_id != org.id:
                raise SystemExit("Existing user belongs to another organization")
            user_result = "reused"
        baseline_summary = seed_legacy_baseline(db, org, baseline_path) if baseline_path else {}
        summary = seed_sample_data(db, org, user) if sample_data else {}
        db.commit()
        print(f"Administrator {user_result}: {user.email}")
        if summary:
            print("Sample data ready:")
            for label, count in summary.items():
                print(f"  {label}: {count}")
        if baseline_summary:
            print("Legacy baseline ready:")
            for label, count in baseline_summary.items():
                print(f"  {label}: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD"))
    parser.add_argument("--name", default=os.getenv("ADMIN_NAME"))
    parser.add_argument("--organization", default="Mutha Wagmal Bhuraji Group")
    parser.add_argument(
        "--sample-data", action="store_true", help="Create an idempotent demonstration dataset"
    )
    parser.add_argument(
        "--baseline",
        nargs="?",
        const="/data/legacy/MWB_Internal_Audit_Manager.html",
        help="Seed all entities, audit areas and checklist items from the legacy HTML",
    )
    args = parser.parse_args()
    if not args.email or not args.password or not args.name:
        parser.error("Provide --email, --password and --name, or ADMIN_EMAIL, ADMIN_PASSWORD and ADMIN_NAME")
    create_admin(
        args.email,
        args.password,
        args.name,
        args.organization,
        args.sample_data,
        args.baseline,
    )
