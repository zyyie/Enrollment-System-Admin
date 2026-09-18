"""HTML email templates for EMS — unified student-facing design."""

import html
import uuid
from datetime import datetime

from shared.services.brand import email_brand_name

APPLICANT_EMAIL_VERSION = "full-summary-v10"
PROFILE_PHOTO_CID = "geranova_profile_photo"


def _compact_day_time(day_time) -> str:
    return str(day_time or "").replace(":00", "").strip()


def _compact_schedule_item(item: dict) -> str:
    section = str(item.get("section") or "").strip()
    day_time = _compact_day_time(item.get("dayTime"))
    slots = item.get("slots")
    prefix = f"[{slots}] " if slots is not None and str(slots).strip() != "" else ""
    if section and day_time:
        return f"{prefix}{section} · {day_time}"
    return section or day_time or "—"


def _unique_email_ref(kind: str, data: dict | None = None) -> str:
    app_number = ""
    if data:
        app_number = str(
            data.get("applicationNumber")
            or data.get("application_number")
            or ""
        ).strip()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    token = uuid.uuid4().hex[:10]
    if app_number:
        return f"{app_number}-{kind}-{stamp}-{token}"
    return f"{kind}-{stamp}-{token}"


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _val(data: dict, *keys: str, default: str = "—") -> str:
    for key in keys:
        raw = data.get(key)
        if raw is not None and str(raw).strip():
            return _esc(str(raw).strip())
    return default


DOC_LABELS = {
    "form_138": "Original Copy of Form 138 (Report Card) signed by the Principal",
    "form_137": "Original Copy of Form 137",
    "good_moral": "Original Copy of Certificate of Good Moral Character",
    "birth_certificate": "Photocopy of Birth Certificate issued by PSA",
    "high_school_diploma": "High School Diploma",
}

DOC_PATH_FIELDS = {
    "form_138": "docForm138Path",
    "form_137": "docForm137Path",
    "good_moral": "docGoodMoralPath",
    "birth_certificate": "docBirthCertificatePath",
    "high_school_diploma": "docHighSchoolDiplomaPath",
}


def _format_applicant_name(app_data: dict) -> str:
    parts = [
        _val(app_data, "lastName"),
        _val(app_data, "firstName"),
        _val(app_data, "middleName"),
    ]
    if parts[0] == "—":
        return "—"
    name = parts[0]
    if parts[1] != "—":
        name += f", {parts[1]}"
    if parts[2] != "—":
        name += f" {parts[2]}"
    return name


def _payment_rows(app_data: dict) -> list[tuple[str, str]]:
    mode = str(app_data.get("paymentMode") or "").strip().lower()
    amount = _val(app_data, "paymentAmount", default="—")
    if amount != "—" and not amount.startswith("PHP"):
        amount = f"PHP {amount}"

    if mode == "gcash":
        return [
            ("Payment Mode", "GCash"),
            ("Amount", amount),
            ("GCash Reference No.", _val(app_data, "gcashReference")),
            ("GCash Sender Name", _val(app_data, "gcashSenderName")),
            ("Payment Receipt", "Submitted" if app_data.get("gcashProofPath") else "—"),
        ]
    if mode == "bank":
        bank_names = {"bpi": "BPI", "unionbank": "UnionBank"}
        bank_code = str(app_data.get("bankCode") or "").strip().lower()
        bank_label = bank_names.get(bank_code, _val(app_data, "bankCode"))
        return [
            ("Payment Mode", "Bank Transfer"),
            ("Bank", bank_label),
            ("Amount", amount),
            ("Bank Reference No.", _val(app_data, "bankReference")),
            ("Account Holder Name", _val(app_data, "bankSenderName")),
            ("Payment Receipt", "Submitted" if app_data.get("bankProofPath") else "—"),
        ]
    return [
        ("Payment Mode", "Pay at Cashier"),
        ("Amount", amount),
        ("Payment Status", _val(app_data, "paymentStatus", default="Pending / Pay at cashier")),
    ]


def _document_rows(app_data: dict) -> list[tuple[str, str]]:
    names = app_data.get("documentFileNames") or {}
    docs = app_data.get("documents") or {}
    rows = []
    for key, label in DOC_LABELS.items():
        filename = None
        if isinstance(names, dict):
            filename = names.get(key)
        if not filename:
            path = docs.get(key) or app_data.get(DOC_PATH_FIELDS.get(key, ""))
            if path:
                filename = str(path).replace("\\", "/").split("/")[-1]
        rows.append((label, _esc(filename) if filename else "—"))
    return rows


def _profile_photo_section_html(app_data: dict) -> str:
    img_src = None
    inline_cid = app_data.get("profilePhotoInlineCid")
    if inline_cid:
        img_src = f"cid:{inline_cid}"
    else:
        data_urls = app_data.get("profilePhotoDataUrls") or {}
        if isinstance(data_urls, dict):
            img_src = data_urls.get("profile") or data_urls.get("profile_upload") or data_urls.get("profile_camera")

    if img_src:
        return (
            '<p style="margin:22px 0 8px;font-size:13px;font-weight:600;color:#1a3a6b;'
            'text-transform:uppercase;letter-spacing:0.4px;">Profile Photo</p>'
            '<div style="margin:0 0 20px;text-align:left;">'
            f'<img src="{img_src}" alt="Profile photo" '
            'style="width:140px;height:140px;object-fit:cover;border-radius:10px;border:1px solid #dee2e6;">'
            '</div>'
        )

    if app_data.get("profilePhotoUploadPath") or app_data.get("profilePhotoCameraPath"):
        return (
            '<p style="margin:22px 0 8px;font-size:13px;font-weight:600;color:#1a3a6b;'
            'text-transform:uppercase;letter-spacing:0.4px;">Profile Photo</p>'
            '<p style="margin:0 0 20px;font-size:14px;color:#334155;">Submitted</p>'
        )
    return ""


def _profile_photo_rows(app_data: dict) -> list[tuple[str, str]]:
    names = app_data.get("profilePhotoFileNames") or {}
    profile_name = names.get("profile") if isinstance(names, dict) else None
    if not profile_name:
        path = app_data.get("profilePhotoUploadPath") or app_data.get("profilePhotoCameraPath")
        if path:
            profile_name = str(path).replace("\\", "/").split("/")[-1]
    return [("Profile Photo", _esc(profile_name) if profile_name else "Submitted")]


def _payment_summary(app_data: dict) -> str:
    mode = str(app_data.get("paymentMode") or "").strip().lower()
    amount = _val(app_data, "paymentAmount", default="")
    peso = f"PHP {amount}" if amount and amount != "—" else ""

    if mode == "gcash":
        if str(app_data.get("paymentStatus") or "").lower() == "submitted":
            summary = (
                f"GCash — Ref: {_val(app_data, 'gcashReference')} · "
                f"{_val(app_data, 'gcashSenderName')} · {peso or '—'}"
            )
            receipt = app_data.get("gcashProofFileName") or app_data.get("gcashProofPath")
            if receipt:
                receipt_name = str(receipt).replace("\\", "/").split("/")[-1]
                summary += f"<br>Receipt: {_esc(receipt_name)}"
            return summary
        return "GCash — Payment not yet submitted"

    if mode == "bank":
        bank_names = {"bpi": "BPI", "unionbank": "UnionBank"}
        bank_code = str(app_data.get("bankCode") or "").strip().lower()
        bank_label = bank_names.get(bank_code, _val(app_data, "bankCode"))
        if str(app_data.get("paymentStatus") or "").lower() == "submitted":
            summary = (
                f"{bank_label} — Ref: {_val(app_data, 'bankReference')} · "
                f"{_val(app_data, 'bankSenderName')} · {peso or '—'}"
            )
            receipt = app_data.get("bankProofFileName") or app_data.get("bankProofPath")
            if receipt:
                receipt_name = str(receipt).replace("\\", "/").split("/")[-1]
                summary += f"<br>Receipt: {_esc(receipt_name)}"
            return summary
        return f"{bank_label} — Payment not yet submitted"

    return "Pay in person at the Cashier"


def _schedule_section_html(app_data: dict) -> str:
    details = app_data.get("subjectScheduleDetails") or []
    if not isinstance(details, list) or not details:
        return ""

    rows_html = ""
    for item in details:
        if not isinstance(item, dict):
            continue
        code = _esc(item.get("code") or "—")
        description = _esc(item.get("description") or "—")
        schedule_text = _esc(_compact_schedule_item(item))
        rows_html += f"""
        <tr>
          <td style="padding:8px 10px;border:1px solid #dee2e6;">{code}</td>
          <td style="padding:8px 10px;border:1px solid #dee2e6;">{description}</td>
          <td style="padding:8px 10px;border:1px solid #dee2e6;">{schedule_text}</td>
        </tr>
        """

    if not rows_html:
        return ""

    grade = _val(app_data, "gradeLevel")
    strand = _val(app_data, "strandCode", "strandId", "strand")
    count = len(details)

    return f"""
      <p style="margin:22px 0 8px;font-size:13px;font-weight:600;color:#1a3a6b;text-transform:uppercase;letter-spacing:0.4px;">Schedule &amp; Strand (1st Semester)</p>
      <p style="margin:0 0 10px;font-size:14px;color:#334155;">
        <strong>Grade:</strong> {grade} · <strong>Strand:</strong> {strand}<br>
        <strong>Preferred schedules:</strong> {count} subject(s)
      </p>
      <table style="width:100%;border-collapse:collapse;margin:0 0 20px;font-size:13px;">
        <thead>
          <tr>
            <th style="padding:8px 10px;background:#f8f9fa;border:1px solid #dee2e6;text-align:left;">Code</th>
            <th style="padding:8px 10px;background:#f8f9fa;border:1px solid #dee2e6;text-align:left;">Subject</th>
            <th style="padding:8px 10px;background:#f8f9fa;border:1px solid #dee2e6;text-align:left;">Schedule</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    """


def _section_table(section_title: str, rows: list[tuple[str, str]]) -> str:
    return f"""
      <p style="margin:22px 0 8px;font-size:13px;font-weight:600;color:#1a3a6b;text-transform:uppercase;letter-spacing:0.4px;">{_esc(section_title)}</p>
      {_info_table(rows)}
    """


def _email_shell(school_name: str, title: str, body_html: str, *, email_ref: str = "") -> str:
    ref = email_ref or _unique_email_ref("mail")
    ref_text = _esc(ref)
    brand = email_brand_name(school_name)
    return f"""
    <!-- ems-mail-start:{ref_text} -->
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:640px;margin:0 auto;color:#1a1a2e;">
      <div style="background:#1a3a6b;color:#ffffff;padding:20px 24px;border-radius:8px 8px 0 0;">
        <h1 style="margin:0;font-size:20px;font-weight:600;">{title}</h1>
        <p style="margin:6px 0 0;font-size:13px;opacity:0.9;">{_esc(brand)}</p>
      </div>
      <div style="background:#ffffff;border:1px solid #dee2e6;border-top:none;padding:24px;border-radius:0 0 8px 8px;line-height:1.65;font-size:15px;">
        {body_html}
        <p style="margin-top:28px;margin-bottom:8px;color:#475569;font-size:14px;">
          Thank you,<br>
          <strong style="color:#1a3a6b;">{_esc(brand)}</strong><br>
          Registrar's Office
        </p>
        <p style="margin:0;color:#64748b;font-size:13px;line-height:1.5;">
          Automated message — contact the Registrar's Office during office hours for inquiries.
          <br><span style="font-size:11px;color:#94a3b8;">Ref: {ref_text}</span>
        </p>
      </div>
    </div>
    <!-- ems-mail-end:{ref_text} -->
    """


def _info_table(rows: list[tuple[str, str]]) -> str:
    body = ""
    for label, value in rows:
        body += f"""
        <tr>
          <td style="padding:10px 12px;background:#f8f9fa;border:1px solid #dee2e6;width:38%;"><strong>{_esc(label)}</strong></td>
          <td style="padding:10px 12px;border:1px solid #dee2e6;">{value}</td>
        </tr>
        """
    return f"""
      <table style="width:100%;border-collapse:collapse;margin:20px 0;font-size:14px;">
        {body}
      </table>
    """


def _callout(title: str, message: str, *, accent: str = "#1a3a6b", background: str = "#e8f0fe") -> str:
    return f"""
      <p style="background:{background};border-left:4px solid {accent};padding:14px 16px;margin:20px 0;border-radius:4px;">
        <strong>{_esc(title)}</strong><br>
        {message}
      </p>
    """


def build_applicant_confirmation_email(app_data: dict, school_name: str) -> str:
    first_name = _val(app_data, "firstName", default="Applicant")
    submitted_on = datetime.now().strftime("%B %d, %Y %I:%M %p")
    email_ref = _unique_email_ref("received", app_data)

    full_address = _val(app_data, "address")
    if full_address == "—":
        address_parts = [
            _val(app_data, "houseNumber"),
            _val(app_data, "street"),
            _val(app_data, "barangay"),
            _val(app_data, "city"),
            _val(app_data, "province"),
        ]
        full_address = ", ".join(p for p in address_parts if p != "—") or "—"

    body = f"""
      <p style="margin-top:0;">Dear <strong>{first_name}</strong>,</p>
      <p>Thank you for submitting your enrollment application. We have successfully received your application and supporting documents.</p>
      <p style="color:#475569;font-size:14px;margin-bottom:0;">Below is a complete copy of the information you reviewed in Step 8 for your records.</p>

      {_section_table("Application Summary", [
          ("Application No.", _val(app_data, "applicationNumber")),
          ("Status", "Pending Review"),
          ("Date Submitted", submitted_on),
      ])}

      {_section_table("Personal Information", [
          ("Full Name", _format_applicant_name(app_data)),
          ("Birthdate", _val(app_data, "birthdate")),
          ("Gender", _val(app_data, "gender")),
          ("Email", _val(app_data, "email")),
          ("Contact Number", _val(app_data, "contactNumber")),
      ])}

      {_section_table("Address", [
          ("House / Unit No.", _val(app_data, "houseNumber")),
          ("Street", _val(app_data, "street")),
          ("Province", _val(app_data, "province")),
          ("City / Municipality", _val(app_data, "city")),
          ("Barangay", _val(app_data, "barangay")),
          ("Full Address", full_address),
      ])}

      {_section_table("Academic Information", [
          ("Grade Level", _val(app_data, "gradeLevel")),
          ("Strand", _val(app_data, "strandCode", "strandId", "strand")),
          ("Admission Type", _val(app_data, "admissionType", default="new").replace("_", " ").title()),
          ("Previous School", _val(app_data, "previousSchool")),
      ])}

      {_profile_photo_section_html(app_data)}

      {_schedule_section_html(app_data)}

      {_section_table("Documents", _document_rows(app_data))}

      {_section_table("Payment", [("Details", _payment_summary(app_data))])}

      {_callout(
          "What happens next?",
          "Our Registrar's Office will review your application. You will receive a separate email titled "
          f"<strong>Enrollment Approved — {_val(app_data, 'applicationNumber')}</strong> if accepted, "
          "including your Student ID and temporary password. Your official Registration Certificate will be "
          "emailed after tuition payment has been approved by the Registrar."
      )}
    """
    return _email_shell(school_name, "Application Received", body, email_ref=email_ref)


def build_admission_approval_email(
    result: dict,
    form_data: dict,
    school_name: str,
) -> str:
    brand = email_brand_name(school_name)
    first_name = _esc(result.get("firstName") or form_data.get("firstName") or "Student")
    student_id = _esc(result.get("studentId") or form_data.get("studentId"))
    temp_password = _esc(result.get("tempPassword") or form_data.get("tempPassword"))
    app_number = _esc(result.get("applicationNumber") or form_data.get("applicationNumber"))
    email_ref = _unique_email_ref("approved", {**form_data, **result})

    body = f"""
      <p style="margin-top:0;">Dear <strong>{first_name}</strong>,</p>
      <p>Congratulations! Application <strong>{app_number}</strong> has been <strong>approved</strong>. You are now officially enrolled at {_esc(brand)}.</p>
      {_info_table([
          ("Application No.", app_number),
          ("Student ID", f"<strong>{student_id}</strong>"),
          ("Password", f"<strong>{temp_password}</strong>"),
          ("Status", "<strong>Approved / Enrolled</strong>"),
      ])}
      {_callout(
          "Student portal login",
          "Sign in using your <strong>Student ID</strong>, <strong>birthdate</strong>, and <strong>temporary password</strong> (case-sensitive)."
      )}
      <p style="margin:0;">Your official <strong>Registration Certificate (PDF)</strong> will be emailed separately after your tuition payment has been approved by the Registrar.</p>
    """
    return _email_shell(brand, "Enrollment Approved", body, email_ref=email_ref)


def build_registration_form_delivery_email(
    result: dict,
    form_data: dict,
    school_name: str,
) -> str:
    """Email body when Registration Certificate is sent after payment approval."""
    first_name = _esc(result.get("firstName") or form_data.get("firstName") or "Student")
    student_id = _esc(result.get("studentId") or form_data.get("studentId"))
    app_number = _esc(result.get("applicationNumber") or form_data.get("applicationNumber"))
    school_year = _esc(form_data.get("schoolYear") or result.get("schoolYear") or "—")
    semester = _esc(form_data.get("semester") or result.get("semester") or "—")
    email_ref = _unique_email_ref("registration-form", {**form_data, **result})

    body = f"""
      <p style="margin-top:0;">Dear <strong>{first_name}</strong>,</p>
      <p>Your tuition payment for <strong>{school_year}</strong> · <strong>{semester}</strong> has been <strong>approved</strong>.</p>
      {_info_table([
          ("Student ID", f"<strong>{student_id}</strong>"),
          ("Application No.", app_number),
          ("School Year", school_year),
          ("Semester", semester),
          ("Status", "<strong>Payment Approved / Enrolled</strong>"),
      ])}
      <p style="margin:0;">Your official <strong>Registration Certificate (PDF)</strong> is attached. Open and save it as proof of enrollment for this term.</p>
    """
    return _email_shell(school_name, "Registration Certificate", body, email_ref=email_ref)


def build_admission_rejection_email(result: dict, reason: str | None, school_name: str) -> str:
    first_name = _esc(result.get("firstName") or "Applicant")
    app_number = _esc(result.get("applicationNumber") or "—")
    email_ref = _unique_email_ref("rejected", result)
    reason_html = ""
    if reason and str(reason).strip():
        reason_html = _callout(
            "Reason",
            _esc(reason),
            accent="#dc2626",
            background="#fef2f2",
        )

    body = f"""
      <p style="margin-top:0;">Dear <strong>{first_name}</strong>,</p>
      <p>Your enrollment application has been reviewed and was <strong>not approved</strong> at this time.</p>
      {_info_table([
          ("Application No.", app_number),
          ("Status", "Not Approved"),
      ])}
      {reason_html}
      {_callout(
          "Need help?",
          "For questions about this decision, please contact the Registrar's Office during office hours."
      )}
    """
    return _email_shell(school_name, "Admission Update", body, email_ref=email_ref)


def build_subject_enrollment_confirmation_email(
    student_data: dict,
    school_name: str,
    *,
    total_units=None,
) -> str:
    first_name = _esc(student_data.get("first_name") or student_data.get("firstName") or "Student")
    student_id = _esc(student_data.get("student_id") or student_data.get("studentId") or "—")
    rows = [
        ("Student ID", student_id),
        ("Status", "Pending Approval"),
    ]
    if total_units is not None:
        rows.append(("Total Units", _esc(total_units)))
    email_ref = _unique_email_ref("subject-enrollment", student_data)

    body = f"""
      <p style="margin-top:0;">Dear <strong>{first_name}</strong>,</p>
      <p>We have received your subject enrollment submission for the current semester.</p>
      {_info_table(rows)}
      {_callout(
          "What happens next?",
          "Your enrollment is pending review by the Administrator. Please wait for a <strong>follow-up email or notification</strong> "
          "once your enrollment has been <strong>approved</strong> or if further action is required."
      )}
      <p style="color:#475569;font-size:14px;margin-bottom:0;">
        You may also check your enrollment status by signing in to the student portal.
      </p>
    """
    return _email_shell(school_name, "Enrollment Submission Received", body, email_ref=email_ref)
