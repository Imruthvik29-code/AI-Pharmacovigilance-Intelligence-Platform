"""Restrict dose-rule access to patient owners and privileged backend roles.

Revision ID: 0008_secure_dose_rules
Revises: 0007_add_dose_rules

The security-only downgrade preserves RLS and records, revokes authenticated
access, and retains service-role CRUD. It intentionally does not restore the
broad privileges inherited by an unprotected 0007-only installation.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008_secure_dose_rules"
down_revision: Union[str, None] = "0007_add_dose_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.medication_dose_rules ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        REVOKE ALL PRIVILEGES ON TABLE public.medication_dose_rules FROM PUBLIC, anon, authenticated, service_role
        """
    )
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.medication_dose_rules TO authenticated, service_role
        """
    )
    op.execute(
        """
        CREATE POLICY "Users manage own dose rules"
        ON public.medication_dose_rules FOR ALL TO authenticated
        USING (EXISTS (
         SELECT 1 FROM public.medications AS m
         JOIN public.patients AS p ON p.id = m.patient_id
         WHERE m.id = medication_dose_rules.medication_id AND p.user_id = auth.uid()
        ))
        WITH CHECK (EXISTS (
         SELECT 1 FROM public.medications AS m
         JOIN public.patients AS p ON p.id = m.patient_id
         WHERE m.id = medication_dose_rules.medication_id AND p.user_id = auth.uid()
        ))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.medication_dose_rules ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        REVOKE ALL PRIVILEGES ON TABLE public.medication_dose_rules FROM PUBLIC, anon, authenticated, service_role
        """
    )
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.medication_dose_rules TO service_role
        """
    )
    op.execute(
        """
        DROP POLICY "Users manage own dose rules" ON public.medication_dose_rules
        """
    )
