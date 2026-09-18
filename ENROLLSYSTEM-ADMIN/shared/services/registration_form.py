"""Generate official SHS registration / enrollment certificate for approved students."""

from __future__ import annotations

import html
import json
import re
import textwrap
from datetime import datetime
from io import BytesIO
from pathlib import Path

from shared.services.brand import email_brand_name

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = ImageDraw = ImageFont = None


def _esc(value) -> str:
    return html.escape(str(value or ""))


def format_student_full_name(data: dict) -> str:
    return ", ".join(
        part for part in (
            _esc(data.get("lastName", "")).upper(),
            _esc(data.get("firstName", "")).upper(),
            _esc(data.get("middleName", "")).upper(),
        ) if part
    )


from shared.services.admission_schedules import (
    _coerce_preferred_map,
    load_admission_schedule_record,
    load_enrollment_schedule_details,
    resolve_subject_schedule_details,
    schedule_rows_have_times,
)


def prepare_form_data(
    result: dict | None,
    app_detail: dict | None = None,
    rest_get_fn=None,
) -> dict:
    merged = {**(app_detail or {}), **(result or {})}
    merged["studentId"] = (
        merged.get("studentId")
        or merged.get("student_id_generated")
        or merged.get("student_id")
        or ""
    )
    merged["tempPassword"] = merged.get("tempPassword") or merged.get("temp_password") or ""
    merged["applicationNumber"] = (
        merged.get("applicationNumber") or merged.get("application_number") or ""
    )
    merged["lastName"] = merged.get("lastName") or merged.get("last_name") or ""
    merged["firstName"] = merged.get("firstName") or merged.get("first_name") or ""
    merged["middleName"] = merged.get("middleName") or merged.get("middle_name") or ""
    merged["gradeLevel"] = merged.get("gradeLevel") or merged.get("grade_level") or ""
    merged["strandCode"] = merged.get("strandCode") or merged.get("strand") or ""
    merged["contactNumber"] = merged.get("contactNumber") or merged.get("contact_number") or ""
    merged["previousSchool"] = merged.get("previousSchool") or merged.get("previous_school") or ""
    merged["admissionType"] = merged.get("admissionType") or merged.get("admission_type") or "new"
    birthdate = merged.get("birthdate") or merged.get("birth_date") or ""
    merged["birthdate"] = str(birthdate)[:10] if birthdate else ""
    merged["schoolYear"] = merged.get("schoolYear") or "2026-2027"
    merged["semester"] = merged.get("semester") or merged.get("semesterCode") or "1st"
    merged["campus"] = merged.get("campus") or "Main Campus"

    existing = merged.get("subjectScheduleDetails")
    if isinstance(existing, list) and existing and schedule_rows_have_times(existing):
        merged["subjectScheduleDetails"] = existing
        merged["financialDetails"] = _resolve_financial_details(merged, rest_get_fn=rest_get_fn)
        return merged

    schedule_record = dict(merged)
    if rest_get_fn and not _coerce_preferred_map(schedule_record):
        fetched = load_admission_schedule_record(
            application_id=str(
                merged.get("id")
                or merged.get("applicationId")
                or ""
            ).strip(),
            application_number=str(
                merged.get("applicationNumber")
                or merged.get("application_number")
                or ""
            ).strip(),
            rest_get_fn=rest_get_fn,
        )
        if fetched:
            schedule_record = {**schedule_record, **fetched}

    schedules = resolve_subject_schedule_details(schedule_record, rest_get_fn)
    if not schedules and rest_get_fn:
        student_id = str(
            merged.get("studentId")
            or merged.get("student_id_generated")
            or merged.get("student_id")
            or ""
        ).strip()
        if student_id:
            schedules = load_enrollment_schedule_details(student_id, rest_get_fn)
    merged["subjectScheduleDetails"] = schedules
    merged["financialDetails"] = _resolve_financial_details(merged, rest_get_fn=rest_get_fn)
    app_no = merged.get("applicationNumber") or merged.get("application_number") or "application"
    if schedules:
        print(f"[Registration form] Loaded {len(schedules)} schedule row(s) for {app_no}")
    else:
        print(f"[Registration form] WARNING: No schedules resolved for {app_no} — COR body will be empty")
    return merged


def _form_context(data: dict, school_name: str) -> dict:
    school_name = email_brand_name(school_name)
    return {
        "school_name": _esc(school_name),
        "full_name": format_student_full_name(data),
        "student_id": _esc(data.get("studentId")),
        "application_number": _esc(data.get("applicationNumber")),
        "approved_on": datetime.now().strftime("%B %d, %Y"),
        "school_year": _esc(data.get("schoolYear") or "2026-2027"),
        "birthdate": _esc(data.get("birthdate")),
        "gender": _esc(data.get("gender")),
        "address": _esc(data.get("address")),
        "contact": _esc(data.get("contactNumber")),
        "email": _esc(data.get("email")),
        "grade_level": _esc(data.get("gradeLevel")),
        "strand": _esc(data.get("strandCode")),
        "admission_type": _esc(str(data.get("admissionType", "new")).title()),
        "previous_school": _esc(data.get("previousSchool")),
    }


def build_registration_form_html(data: dict, school_name: str) -> str:
    ctx = _form_context(data, school_name)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Certificate of Registration — {ctx['student_id']}</title>
  <style>
    @page {{ margin: 18mm; }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: "Times New Roman", Times, serif;
      color: #111;
      max-width: 820px;
      margin: 0 auto;
      padding: 28px;
      line-height: 1.5;
      background: #fff;
    }}
    .certificate {{
      border: 3px double #1a3a6b;
      padding: 28px 32px;
    }}
    .header {{
      text-align: center;
      border-bottom: 2px solid #1a3a6b;
      padding-bottom: 16px;
      margin-bottom: 20px;
    }}
    .header h1 {{
      margin: 0;
      font-size: 24px;
      color: #1a3a6b;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }}
    .header h2 {{
      margin: 8px 0 0;
      font-size: 17px;
      font-weight: normal;
      color: #334155;
    }}
    .status {{
      display: inline-block;
      margin-top: 12px;
      padding: 8px 18px;
      background: #ecfdf5;
      border: 2px solid #059669;
      color: #065f46;
      font-weight: bold;
      font-size: 14px;
      letter-spacing: 1px;
    }}
    .student-name {{
      text-align: center;
      margin: 24px 0;
      padding: 18px;
      background: #f8fafc;
      border: 1px solid #cbd5e1;
    }}
    .student-name label {{
      display: block;
      font-size: 12px;
      letter-spacing: 1px;
      text-transform: uppercase;
      color: #64748b;
      margin-bottom: 8px;
    }}
    .student-name strong {{
      display: block;
      font-size: 26px;
      color: #1a3a6b;
      letter-spacing: 0.5px;
    }}
    .certify {{
      text-align: center;
      font-size: 15px;
      margin: 18px 0 24px;
      color: #334155;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 14px 0;
    }}
    th, td {{
      border: 1px solid #333;
      padding: 9px 12px;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      width: 34%;
      background: #f8fafc;
      text-align: left;
      font-weight: bold;
    }}
    .section-title {{
      margin: 22px 0 8px;
      font-size: 14px;
      font-weight: bold;
      color: #1a3a6b;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .signatures {{
      margin-top: 48px;
      display: flex;
      justify-content: space-between;
      gap: 24px;
    }}
    .signatures div {{
      width: 45%;
      text-align: center;
      font-size: 13px;
    }}
    .line {{
      border-top: 1px solid #111;
      margin: 42px 0 6px;
    }}
    .footer-note {{
      margin-top: 20px;
      font-size: 12px;
      color: #64748b;
      text-align: center;
    }}
    @media print {{
      body {{ padding: 0; }}
      .no-print {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div class="certificate">
    <div class="header">
      <h1>{ctx['school_name']}</h1>
      <h2>Certificate of Registration — Senior High School</h2>
      <div class="status">OFFICIALLY ENROLLED</div>
    </div>

    <p class="certify">
      This is to certify that the student named below is <strong>registered and enrolled</strong>
      at {ctx['school_name']} for School Year <strong>{ctx['school_year']}</strong>.
    </p>

    <div class="student-name">
      <label>Registered Student</label>
      <strong>{ctx['full_name']}</strong>
    </div>

    <div class="section-title">Registration Details</div>
    <table>
      <tr><th>Student ID</th><td><strong>{ctx['student_id']}</strong></td></tr>
      <tr><th>Application No.</th><td>{ctx['application_number']}</td></tr>
      <tr><th>Date Approved</th><td>{ctx['approved_on']}</td></tr>
      <tr><th>School Year</th><td>{ctx['school_year']}</td></tr>
      <tr><th>Enrollment Status</th><td><strong>Approved / Enrolled</strong></td></tr>
    </table>

    <div class="section-title">Student Information</div>
    <table>
      <tr><th>Full Name</th><td>{ctx['full_name']}</td></tr>
      <tr><th>Birthdate</th><td>{ctx['birthdate']}</td></tr>
      <tr><th>Gender</th><td>{ctx['gender']}</td></tr>
      <tr><th>Address</th><td>{ctx['address']}</td></tr>
      <tr><th>Contact Number</th><td>{ctx['contact']}</td></tr>
      <tr><th>Email</th><td>{ctx['email']}</td></tr>
    </table>

    <div class="section-title">Academic Information</div>
    <table>
      <tr><th>Grade Level</th><td>{ctx['grade_level']}</td></tr>
      <tr><th>Strand</th><td>{ctx['strand']}</td></tr>
      <tr><th>Admission Type</th><td>{ctx['admission_type']}</td></tr>
      <tr><th>Previous School</th><td>{ctx['previous_school'] or '—'}</td></tr>
    </table>

    <div class="signatures">
      <div>
        <div class="line"></div>
        Student / Parent-Guardian Signature<br>
        <em>Date: ___________________</em>
      </div>
      <div>
        <div class="line"></div>
        Registrar / Authorized Signatory<br>
        <em>{ctx['school_name']}</em>
      </div>
    </div>

    <p class="footer-note">
      Official document generated by the {ctx['school_name']} Enrollment System.
      Present this certificate when requested by the registrar.
    </p>
  </div>
  <p class="no-print" style="text-align:center;color:#64748b;font-family:Arial,sans-serif;font-size:13px;">
    Tip: Use Print → Save as PDF to keep a PDF copy.
  </p>
</body>
</html>
"""


def build_registration_form_email_html(data: dict, school_name: str) -> str:
    """Email-safe inline version — renders inside Gmail/Outlook body."""
    ctx = _form_context(data, school_name)
    return f"""
<div style="margin:28px 0 0;padding:0;font-family:Georgia,'Times New Roman',serif;color:#111;">
  <div style="border:3px double #1a3a6b;padding:24px;background:#fff;">
    <div style="text-align:center;border-bottom:2px solid #1a3a6b;padding-bottom:14px;margin-bottom:18px;">
      <div style="font-size:22px;font-weight:bold;color:#1a3a6b;text-transform:uppercase;">{ctx['school_name']}</div>
      <div style="font-size:16px;color:#334155;margin-top:6px;">Certificate of Registration — Senior High School</div>
      <div style="display:inline-block;margin-top:12px;padding:8px 16px;background:#ecfdf5;border:2px solid #059669;color:#065f46;font-weight:bold;font-size:13px;letter-spacing:1px;">OFFICIALLY ENROLLED</div>
    </div>
    <p style="text-align:center;font-size:15px;color:#334155;margin:0 0 18px;">
      This certifies that the student below is <strong>registered and enrolled</strong>
      for School Year <strong>{ctx['school_year']}</strong>.
    </p>
    <div style="text-align:center;padding:16px;background:#f8fafc;border:1px solid #cbd5e1;margin-bottom:18px;">
      <div style="font-size:11px;letter-spacing:1px;text-transform:uppercase;color:#64748b;">Registered Student</div>
      <div style="font-size:24px;font-weight:bold;color:#1a3a6b;margin-top:8px;">{ctx['full_name']}</div>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:16px;">
      <tr><td style="border:1px solid #333;padding:8px;background:#f8fafc;width:34%;font-weight:bold;">Student ID</td><td style="border:1px solid #333;padding:8px;"><strong>{ctx['student_id']}</strong></td></tr>
      <tr><td style="border:1px solid #333;padding:8px;background:#f8fafc;font-weight:bold;">Application No.</td><td style="border:1px solid #333;padding:8px;">{ctx['application_number']}</td></tr>
      <tr><td style="border:1px solid #333;padding:8px;background:#f8fafc;font-weight:bold;">Date Approved</td><td style="border:1px solid #333;padding:8px;">{ctx['approved_on']}</td></tr>
      <tr><td style="border:1px solid #333;padding:8px;background:#f8fafc;font-weight:bold;">Grade Level</td><td style="border:1px solid #333;padding:8px;">{ctx['grade_level']}</td></tr>
      <tr><td style="border:1px solid #333;padding:8px;background:#f8fafc;font-weight:bold;">Strand</td><td style="border:1px solid #333;padding:8px;">{ctx['strand']}</td></tr>
      <tr><td style="border:1px solid #333;padding:8px;background:#f8fafc;font-weight:bold;">Status</td><td style="border:1px solid #333;padding:8px;"><strong>Approved / Enrolled</strong></td></tr>
    </table>
    <p style="font-size:12px;color:#64748b;text-align:center;margin:0;">
      Your official registration certificate is attached as a PNG image. Open the attachment to view or save it.
    </p>
  </div>
</div>
"""


def build_approval_email_html(result: dict, form_data: dict, school_name: str) -> str:
    from shared.services.email_templates import build_admission_approval_email

    return build_admission_approval_email(result, form_data, school_name)

def _load_font(size: int, bold: bool = False):
    if ImageFont is None:
        return None
    candidates = []
    if bold:
        candidates.extend([
            "C:/Windows/Fonts/timesbd.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        ])
    else:
        candidates.extend([
            "C:/Windows/Fonts/times.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        ])
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, width: int) -> list[str]:
    clean = " ".join(str(text or "—").split())
    if not clean:
        return ["—"]
    return textwrap.wrap(clean, width=width) or ["—"]


def _draw_centered_text(draw, text, y, width, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text(((width - text_w) / 2, y), text, font=font, fill=fill)
    return y + (bbox[3] - bbox[1]) + 8


def _draw_label_value_block(draw, x, y, width, label, value, label_font, value_font, line_gap=6):
    label_lines = _wrap_text(label, 24)
    value_lines = _wrap_text(value, 42)
    row_height = max(len(label_lines), len(value_lines)) * 22 + 16
    draw.rectangle([x, y, x + width, y + row_height], outline="#333333", width=1)
    draw.rectangle([x, y, x + int(width * 0.34), y + row_height], fill="#f8fafc", outline="#333333", width=1)
    ly = y + 8
    for line in label_lines:
        draw.text((x + 12, ly), line, font=label_font, fill="#111111")
        ly += 20
    vy = y + 8
    for line in value_lines:
        draw.text((x + int(width * 0.34) + 12, vy), line, font=value_font, fill="#111111")
        vy += 20
    return y + row_height


def build_registration_certificate_png(data: dict, school_name: str) -> bytes:
    if Image is None:
        raise RuntimeError("Pillow is required to generate registration certificate images.")

    ctx = _form_context(data, school_name)
    width, height = 1240, 1754
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    title_font = _load_font(34, bold=True)
    subtitle_font = _load_font(24)
    badge_font = _load_font(20, bold=True)
    section_font = _load_font(18, bold=True)
    label_font = _load_font(18, bold=True)
    value_font = _load_font(18)
    name_label_font = _load_font(16)
    name_font = _load_font(34, bold=True)
    body_font = _load_font(18)
    small_font = _load_font(15)

    margin = 70
    inner_left = margin + 24
    inner_right = width - margin - 24
    content_width = inner_right - inner_left

    draw.rectangle([margin, margin, width - margin, height - margin], outline="#1a3a6b", width=4)
    draw.rectangle([margin + 8, margin + 8, width - margin - 8, height - margin - 8], outline="#1a3a6b", width=2)

    y = margin + 36
    y = _draw_centered_text(draw, school_name.upper(), y, width, title_font, "#1a3a6b")
    y = _draw_centered_text(draw, "Certificate of Registration — Senior High School", y, width, subtitle_font, "#334155")

    badge_text = "OFFICIALLY ENROLLED"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = badge_bbox[2] - badge_bbox[0] + 36
    badge_h = badge_bbox[3] - badge_bbox[1] + 18
    badge_x = (width - badge_w) / 2
    draw.rectangle([badge_x, y, badge_x + badge_w, y + badge_h], fill="#ecfdf5", outline="#059669", width=2)
    draw.text((badge_x + 18, y + 8), badge_text, font=badge_font, fill="#065f46")
    y += badge_h + 24

    certify = (
        f"This certifies that the student below is registered and enrolled at {school_name} "
        f"for School Year {ctx['school_year']}."
    )
    for line in _wrap_text(certify, 78):
        y = _draw_centered_text(draw, line, y, width, body_font, "#334155")

    name_box_top = y + 10
    name_box_bottom = name_box_top + 110
    draw.rectangle([inner_left, name_box_top, inner_right, name_box_bottom], fill="#f8fafc", outline="#cbd5e1", width=2)
    _draw_centered_text(draw, "REGISTERED STUDENT", name_box_top + 16, width, name_label_font, "#64748b")
    full_name = format_student_full_name(data)
    _draw_centered_text(draw, full_name, name_box_top + 48, width, name_font, "#1a3a6b")
    y = name_box_bottom + 24

    def section(title):
        nonlocal y
        draw.text((inner_left, y), title.upper(), font=section_font, fill="#1a3a6b")
        y += 30

    def row(label, value):
        nonlocal y
        y = _draw_label_value_block(draw, inner_left, y, content_width, label, value, label_font, value_font)

    section("Registration Details")
    row("Student ID", ctx["student_id"])
    row("Application No.", ctx["application_number"])
    row("Date Approved", ctx["approved_on"])
    row("School Year", ctx["school_year"])
    row("Enrollment Status", "Approved / Enrolled")

    section("Student Information")
    row("Full Name", full_name)
    row("Birthdate", ctx["birthdate"])
    row("Gender", ctx["gender"])
    row("Address", ctx["address"])
    row("Contact Number", ctx["contact"])
    row("Email", ctx["email"])

    section("Academic Information")
    row("Grade Level", ctx["grade_level"])
    row("Strand", ctx["strand"])
    row("Admission Type", ctx["admission_type"])
    row("Previous School", ctx["previous_school"] or "—")

    sig_y = max(y + 36, height - margin - 170)
    left_x = inner_left + 40
    right_x = inner_right - 280
    draw.line([left_x, sig_y, left_x + 280, sig_y], fill="#111111", width=1)
    draw.line([right_x, sig_y, right_x + 280, sig_y], fill="#111111", width=1)
    draw.text((left_x + 20, sig_y + 10), "Student / Parent-Guardian Signature", font=small_font, fill="#111111")
    draw.text((left_x + 70, sig_y + 34), "Date: ___________________", font=small_font, fill="#111111")
    draw.text((right_x + 20, sig_y + 10), "Registrar / Authorized Signatory", font=small_font, fill="#111111")
    draw.text((right_x + 40, sig_y + 34), school_name, font=small_font, fill="#111111")

    footer = "Official document generated by the enrollment system. Present this certificate when requested by the registrar."
    _draw_centered_text(draw, footer, height - margin - 42, width, small_font, "#64748b")

    buffer = BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def save_registration_certificate_png(root: Path, data: dict, school_name: str) -> str:
    student_id = (
        data.get("studentId")
        or data.get("student_id_generated")
        or data.get("applicationNumber")
        or "student"
    )
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(student_id))
    out_dir = root / "uploads" / "registration-forms"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{safe_id}_Registration_Certificate.png"
    target = out_dir / filename
    target.write_bytes(build_registration_certificate_png(data, school_name))
    return str(target.relative_to(root)).replace("\\", "/")


def format_student_full_name_plain(data: dict) -> str:
    return ", ".join(
        part for part in (
            str(data.get("lastName", "")).upper(),
            str(data.get("firstName", "")).upper(),
            str(data.get("middleName", "")).upper(),
        ) if part
    )


def _resolve_school_logo_path() -> Path | None:
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        for name in ("school-logo.png", "geranova-logo.png"):
            candidate = ancestor / "assets" / name
            if candidate.is_file():
                return candidate
    return None


_LOGO_PDF_BYTES: bytes | None = None


def _prepare_logo_image_for_pdf(img: "Image.Image") -> "Image.Image":
    """Strip dark backgrounds and flatten transparency onto white for PDF embedding."""
    img = img.convert("RGBA")
    pixels = img.load()
    width, height = img.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha and red < 48 and green < 48 and blue < 48:
                pixels[x, y] = (255, 255, 255, 0)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    white = Image.new("RGBA", img.size, (255, 255, 255, 255))
    flattened = Image.alpha_composite(white, img).convert("RGB")
    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
    flattened.thumbnail((180, 180), resample)
    return flattened


def _logo_bytes_for_pdf() -> bytes | None:
    """Return a small PNG logo (white background, no black box) for COR PDFs."""
    global _LOGO_PDF_BYTES
    if _LOGO_PDF_BYTES is not None:
        return _LOGO_PDF_BYTES or None

    logo_path = _resolve_school_logo_path()
    if not logo_path:
        _LOGO_PDF_BYTES = b""
        return None

    if Image is None:
        _LOGO_PDF_BYTES = logo_path.read_bytes()
        return _LOGO_PDF_BYTES

    try:
        with Image.open(logo_path) as img:
            prepared = _prepare_logo_image_for_pdf(img)
            buffer = BytesIO()
            prepared.save(buffer, format="PNG", optimize=True)
            _LOGO_PDF_BYTES = buffer.getvalue()
            return _LOGO_PDF_BYTES
    except Exception:
        _LOGO_PDF_BYTES = logo_path.read_bytes()
        return _LOGO_PDF_BYTES


def _pdf_text(value) -> str:
    """Helvetica in fpdf2 is Latin-1 only — normalize common Unicode punctuation."""
    text = str(value or "-")
    return (
        text.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


def _school_year_short(school_year: str) -> str:
    text = str(school_year or "").strip()
    match = re.match(r"(\d{4})\s*[-–]\s*(\d{4})", text)
    if match:
        return f"{match.group(1)[-2:]}{match.group(2)[-2:]}"
    digits = re.sub(r"\D", "", text)
    return digits[-4:] if len(digits) >= 4 else text or "2627"


def _semester_label(data: dict) -> str:
    raw = str(data.get("semester") or data.get("semesterCode") or "1st").lower()
    if raw in {"2nd", "2", "second"} or "second" in raw or "2nd" in raw:
        return "Second Semester"
    return "First Semester"


def _expand_day_code(code: str) -> str:
    parts = []
    i = 0
    text = str(code or "")
    while i < len(text):
        if text[i:i + 2] == "Th":
            parts.append("Thu")
            i += 2
        elif text[i:i + 2] == "Sa":
            parts.append("Sat")
            i += 2
        elif text[i] == "M":
            parts.append("Mon")
            i += 1
        elif text[i] == "T":
            parts.append("Tue")
            i += 1
        elif text[i] == "W":
            parts.append("Wed")
            i += 1
        elif text[i] == "F":
            parts.append("Fri")
            i += 1
        else:
            i += 1
    if not parts:
        return code or "TBA"
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} & {parts[1]}"
    return f"{', '.join(parts[:-1])} & {parts[-1]}"


def _format_readable_time(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"(\d)(am|pm)\b", r"\1 \2", text, flags=re.I)
    text = re.sub(r"\bam\b", "AM", text, flags=re.I)
    text = re.sub(r"\bpm\b", "PM", text, flags=re.I)
    text = re.sub(r"(\d)(AM|PM)\b", r"\1 \2", text)
    return re.sub(r"\s+", " ", text).strip()


def _format_schedule_display(day_time: str, section: str = "") -> str:
    text = str(day_time or "").strip()
    if not text:
        return _pdf_text(section or "TBA")
    match = re.match(r"^(\S+)\s+(.+)$", text)
    if not match:
        return _pdf_text(text)
    days = _expand_day_code(match.group(1))
    time_part = match.group(2)
    if "-" in time_part:
        start, end = time_part.split("-", 1)
        time_text = f"{_format_readable_time(start.strip())} - {_format_readable_time(end.strip())}"
    else:
        time_text = _format_readable_time(time_part)
    return _pdf_text(f"{days} · {time_text}")


def _program_description(data: dict) -> str:
    grade = str(data.get("gradeLevel") or "").strip()
    strand = str(data.get("strandCode") or "").strip()
    if grade and strand:
        return f"{grade} — {strand} Track (Senior High School)"
    if grade:
        return f"{grade} — Senior High School"
    if strand:
        return f"{strand} Track — Senior High School"
    return "Senior High School"


def _extract_section_label(schedules: list) -> str:
    for item in schedules:
        if not isinstance(item, dict):
            continue
        section = str(item.get("section") or "").strip()
        if section:
            return section
    return "-"


def _total_units(schedules: list) -> float:
    total = 0.0
    for item in schedules:
        if not isinstance(item, dict):
            continue
        try:
            total += float(item.get("units") or 0)
        except (TypeError, ValueError):
            continue
    if total.is_integer():
        return int(total)
    return round(total, 1)


def _format_money(amount) -> str:
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0
    return f"{value:,.2f}"


def _money_in_parens(amount) -> str:
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value <= 0:
        return "-"
    return f"({_format_money(value)})"


def _split_assessment(total: float) -> dict:
    total = max(float(total or 0), 0.0)
    if total <= 0:
        return {"tuition": 0.0, "other": 0.0, "misc": 0.0, "total": 0.0}
    tuition = round(total * 0.70, 2)
    other = round(total * 0.22, 2)
    misc = round(total - tuition - other, 2)
    return {"tuition": tuition, "other": other, "misc": misc, "total": total}


def _term_code_label(data: dict) -> str:
    raw = str(data.get("semester") or data.get("semesterCode") or "1st").lower()
    if raw in {"2nd", "2", "second"} or "second" in raw or "2nd" in raw:
        return "2nd"
    return "1st"


def _resolve_latest_enrollment_id(student_id: str, rest_get_fn, semester_code: str | None = None):
    sid = str(student_id or "").strip().upper()
    if not sid or not rest_get_fn:
        return None

    students, err = rest_get_fn(
        "students",
        f"student_id=eq.{sid}&select=id",
        True,
        12,
    )
    if err or not students:
        return None

    student_uuid = students[0].get("id")
    if not student_uuid:
        return None

    enrollments, err = rest_get_fn(
        "enrollments",
        (
            f"student_id=eq.{student_uuid}&status=eq.enrolled"
            "&select=id,semester_id,semesters(code)"
            "&order=created_at.desc"
        ),
        True,
        12,
    )
    if err or not enrollments:
        return None

    target_sem = (semester_code or "").strip().lower()
    if target_sem:
        for row in enrollments:
            sem = row.get("semesters") or {}
            code = str(sem.get("code") or "").lower()
            if code == target_sem or (target_sem == "1st" and code in ("1st", "first")) or (
                target_sem == "2nd" and code in ("2nd", "second")
            ):
                return row.get("id")
    return enrollments[0].get("id")


def load_enrollment_financial_details(
    student_id: str | None = None,
    rest_get_fn=None,
    semester_code: str | None = None,
) -> dict:
    """Load semester payment receipt figures for the registration form."""
    enrollment_id = _resolve_latest_enrollment_id(student_id, rest_get_fn, semester_code)
    if not enrollment_id or not rest_get_fn:
        return {}

    rows, err = rest_get_fn(
        "enrollment_payments",
        (
            f"enrollment_id=eq.{enrollment_id}"
            "&select=assessment_amount,amount_paid,balance,status,or_number,payment_date,payment_mode"
        ),
        True,
        12,
    )
    if err or not rows:
        return {}

    row = rows[0]
    assessment = float(row.get("assessment_amount") or 0)
    paid = float(row.get("amount_paid") or 0)
    balance = float(row.get("balance") if row.get("balance") is not None else max(assessment - paid, 0))
    return {
        "assessmentAmount": assessment,
        "amountPaid": paid,
        "balance": balance,
        "status": row.get("status") or "",
        "orNumber": row.get("or_number") or "",
        "paymentDate": str(row.get("payment_date") or "")[:10],
        "paymentMode": row.get("payment_mode") or "",
    }


def _resolve_financial_details(data: dict, rest_get_fn=None) -> dict:
    financial = load_enrollment_financial_details(
        data.get("studentId"),
        rest_get_fn=rest_get_fn,
        semester_code=_term_code_label(data),
    )

    assessment = float(financial.get("assessmentAmount") or 0)
    if assessment <= 0:
        try:
            assessment = float(data.get("paymentAmount") or 0)
        except (TypeError, ValueError):
            assessment = 0.0
    if assessment <= 0:
        assessment = 2500.0

    paid = float(financial.get("amountPaid") or 0)
    if paid <= 0 and str(financial.get("status") or "").lower() == "approved":
        paid = assessment
    if paid <= 0:
        try:
            admission_paid = float(data.get("paymentAmount") or 0)
        except (TypeError, ValueError):
            admission_paid = 0.0
        if admission_paid > 0 and str(data.get("paymentStatus") or "").lower() in ("approved", "submitted", "paid"):
            paid = min(admission_paid, assessment)

    balance = float(financial.get("balance") if financial.get("balance") is not None else max(assessment - paid, 0))
    charges = _split_assessment(assessment)
    return {
        **financial,
        "assessmentAmount": assessment,
        "amountPaid": paid,
        "balance": balance,
        "charges": charges,
        "termCode": _term_code_label(data),
    }


COR_PDF_LAYOUT_VERSION = "v9"


def build_registration_certificate_pdf(data: dict, school_name: str) -> bytes:
    try:
        from fpdf import FPDF
    except ImportError as err:
        raise RuntimeError("fpdf2 is required for PDF certificates. Run: pip install fpdf2") from err

    ctx = _form_context(data, school_name)
    full_name = _pdf_text(format_student_full_name_plain(data))
    schedules = data.get("subjectScheduleDetails") or []
    if not isinstance(schedules, list):
        schedules = []

    # Landscape A4
    page_w, page_h = 297.0, 210.0
    mx = 12.0
    content_w = page_w - 24.0
    black = (15, 23, 42)
    muted = (100, 116, 139)

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_margin(0)
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    def fit(text: str, max_w: float, size: int = 7, bold: bool = False) -> str:
        pdf.set_font("Helvetica", "B" if bold else "", size)
        text = _pdf_text(text)
        if pdf.get_string_width(text) <= max_w:
            return text
        ell = "..."
        while text and pdf.get_string_width(text + ell) > max_w:
            text = text[:-1]
        return (text + ell) if text else "-"

    def write(x: float, y: float, text: str, size: int = 7, bold: bool = False, color=black, max_w: float | None = None):
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.set_text_color(*color)
        shown = fit(text, max_w, size, bold) if max_w else _pdf_text(text)
        pdf.text(x, y, shown)

    def write_center(cx: float, y: float, width: float, text: str, size: int = 7, bold: bool = False, color=black):
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.set_text_color(*color)
        shown = fit(text, width - 2, size, bold)
        tw = pdf.get_string_width(shown)
        pdf.text(cx + (width - tw) / 2, y, shown)

    def write_right(x_right: float, y: float, text: str, size: int = 7, bold: bool = False, color=black):
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.set_text_color(*color)
        shown = _pdf_text(text)
        tw = pdf.get_string_width(shown)
        pdf.text(x_right - tw, y, shown)

    def hline(x1, y1, x2, y2, width=0.2):
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(width)
        pdf.line(x1, y1, x2, y2)

    def table_box(x, y, w, h):
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.2)
        pdf.rect(x, y, w, h)

    # Header (COR PDF — no logo, no SCHOOL_NAME line)
    hy = 10.0
    write_center(mx, hy + 8, content_w, "Republic of the Philippines", size=7.5)
    write_center(mx, hy + 14, content_w, "Senior High School", size=11, bold=True)
    title_y = hy + 22
    write_center(mx, title_y, content_w, "CERTIFICATE OF REGISTRATION", size=13, bold=True)

    header_bottom = title_y + 7

    # Student info
    y = header_bottom + 4
    write(mx, y, full_name, size=11, bold=True, max_w=content_w * 0.62)
    write_right(mx + content_w, y, f"A.Y. {_school_year_short(ctx['school_year'])}", size=11, bold=True)
    y += 6
    write(mx, y, ctx["student_id"], size=9, max_w=content_w * 0.62)
    write_right(mx + content_w, y, f"TERM: {_semester_label(data).upper()}", size=9, bold=True)
    y += 5
    hline(mx, y, mx + content_w, y)
    y += 5

    program = _pdf_text(_program_description(data))
    strand_code = _pdf_text(ctx["strand"] or "-")
    section_label = _extract_section_label(schedules)

    write(mx, y, "PROGRAM / STRAND:", size=6.5, color=muted)
    write(mx + 34, y, program, size=8, bold=True, max_w=content_w * 0.58)
    write_right(mx + content_w, y, f"STRAND CODE: {strand_code}", size=8, bold=True)
    y += 5
    write(
        mx, y,
        f"Grade Level: {ctx['grade_level'] or '-'}  |  Section: {section_label}  |  Campus: {_pdf_text(data.get('campus') or 'Main Campus')}",
        size=7, max_w=content_w * 0.72,
    )
    write_right(mx + content_w, y, f"App No.: {ctx['application_number'] or '-'}", size=7)
    y += 4
    write(mx, y, f"Date Registered: {ctx['approved_on']}  |  Contact: {ctx['contact'] or '-'}", size=7, max_w=content_w)
    y += 4
    if ctx["address"]:
        write(mx, y, f"Address: {ctx['address']}", size=7, max_w=content_w)
        y += 4
    y += 2
    hline(mx, y, mx + content_w, y)
    y += 4

    # Subject schedule table
    cols = [
        ("SUBJECT CODE", 28),
        ("SUBJECT TITLE", 92),
        ("SECTION", 38),
        ("UNITS", 16),
        ("SCHEDULE", content_w - 28 - 92 - 38 - 16),
    ]
    th = 6.0
    table_box(mx, y, content_w, th)
    x = mx
    for title, width in cols:
        write_center(x, y + 4.2, width, title, size=6.5, bold=True)
        if x > mx:
            hline(x, y, x, y + th)
        x += width
    y += th

    row_h_subj = 4.3
    fin_block_reserve = 83.0  # FINANCIAL title + box + disclaimer/footer band
    max_rows = max(1, int((page_h - y - fin_block_reserve) / row_h_subj))
    display_rows = schedules[:max_rows] if schedules else []

    if not display_rows:
        table_box(mx, y, content_w, row_h_subj)
        write_center(mx, y + 3.4, content_w, "Schedule will be finalized upon enrollment.", size=7, color=muted)
        y += row_h_subj
    else:
        for item in display_rows:
            if not isinstance(item, dict):
                continue
            code = _pdf_text(item.get("code") or "-")
            title = _pdf_text(item.get("description") or "-")
            section = _pdf_text(item.get("section") or section_label)
            units = _pdf_text(item.get("units") or "-")
            schedule = _format_schedule_display(item.get("dayTime") or "", section)
            table_box(mx, y, content_w, row_h_subj)
            x = mx
            values = [code, title, section, str(units), schedule]
            for value, (_, width) in zip(values, cols):
                write(x + 1.5, y + 3.4, value, size=6.5, max_w=width - 3)
                if x > mx:
                    hline(x, y, x, y + row_h_subj)
                x += width
            y += row_h_subj

        if len(schedules) > len(display_rows):
            table_box(mx, y, content_w, row_h_subj)
            write_center(
                mx, y + 3.4, content_w,
                f"... and {len(schedules) - len(display_rows)} more subject(s)",
                size=6.5, color=muted,
            )
            y += row_h_subj

    total_units = _total_units(schedules)
    sum_h = 6.0
    table_box(mx, y, content_w, sum_h)
    write(mx + 3, y + 4.2, f"TOTAL UNITS: {total_units}", size=7, bold=True)
    write_center(mx, y + 4.2, content_w, "ENROLLMENT STATUS: OFFICIALLY ENROLLED", size=7, bold=True)
    write_right(mx + content_w - 3, y + 4.2, f"SUBJECTS: {len(schedules)}", size=7, bold=True)
    y += sum_h + 2

    financial = data.get("financialDetails") or _resolve_financial_details(data)
    charges = financial.get("charges") or _split_assessment(financial.get("assessmentAmount"))
    assessment = float(financial.get("assessmentAmount") or charges.get("total") or 0)
    amount_paid = float(financial.get("amountPaid") or 0)
    balance = float(
        financial.get("balance")
        if financial.get("balance") is not None
        else max(assessment - amount_paid, 0)
    )
    term_code = financial.get("termCode") or _term_code_label(data)
    sy_label = ctx["school_year"] or "2026-2027"

    fin_title_y = y + 2
    write_center(mx, fin_title_y, content_w, "FINANCIAL", size=8, bold=True)
    y += 5

    col_gap = 4.0
    col_w = (content_w - col_gap) / 2
    left_x = mx
    right_x = mx + col_w + col_gap
    fin_top = y
    row_step = 3.8

    def fin_row(lx, ly, label, value, label_w=52, bold_value=False):
        write(lx + 2, ly, label, size=6.2, max_w=label_w)
        if value:
            write_right(lx + col_w - 2, ly, value, size=6.2, bold=bold_value)

    def fin_divider(lx, ly):
        hline(lx + 1.5, ly, lx + col_w - 1.5, ly, width=0.15)

    def fin_gap(ly_ref, amount):
        return ly_ref + amount

    ly = fin_top + 4.5
    ry = fin_top + 4.5
    write(left_x + 2, ly, f"CHARGES for {sy_label}/{term_code} Term", size=6.2, bold=True, max_w=col_w - 4)
    write(right_x + 2, ry, "PAYMENTS AND OTHER ADJUSTMENTS", size=6.2, bold=True, max_w=col_w - 4)
    ly += 4.5
    ry += 4.5

    fin_row(left_x, ly, "TUITION FEES", _format_money(charges.get("tuition")))
    fin_row(right_x, ry, "PAYMENT", _money_in_parens(amount_paid) if amount_paid else "-")
    ly += row_step
    ry += row_step

    fin_row(left_x, ly, "OTHER SCHOOL FEES", _format_money(charges.get("other")))
    fin_row(right_x, ry, "REFUND", "-")
    ly += row_step
    ry += row_step

    fin_row(left_x, ly, "MISCELLANEOUS FEES", _format_money(charges.get("misc")))
    ly += row_step

    ly = fin_gap(ly, 1.0)
    ry = fin_gap(ry, 1.0)
    fin_divider(left_x, ly)
    fin_divider(right_x, ry)
    ly = fin_gap(ly, 2.4)
    ry = fin_gap(ry, 2.4)

    fin_row(left_x, ly, "Total Assessment", _format_money(assessment), bold_value=True)
    fin_row(right_x, ry, "Net Balance", _format_money(balance), bold_value=True)
    ly += row_step
    ry += row_step

    fin_row(left_x, ly, "Net Assessment", _format_money(assessment), bold_value=True)
    fin_row(right_x, ry, "Total Current Balance", _format_money(balance), bold_value=True)
    ly += row_step

    meta_y = ly + 1.0
    if financial.get("orNumber"):
        write(left_x + 2, meta_y, f"O.R. No.: {financial.get('orNumber')}", size=6, color=muted)
        meta_y += 3.2
    if financial.get("paymentDate"):
        write(left_x + 2, meta_y, f"Payment Date: {financial.get('paymentDate')}", size=6, color=muted)

    ry = fin_gap(ry, 2.5)
    fin_divider(right_x, ry)
    ry = fin_gap(ry, 2.5)
    write(right_x + 2, ry, "PAYMENT SCHEDULE", size=6.2, bold=True)
    ry = fin_gap(ry, 4.0)

    if balance <= 0:
        fin_row(right_x, ry, "Status", "FULLY PAID", label_w=30)
        ry += row_step
        fin_row(right_x, ry, "Amount Settled", _format_money(amount_paid), label_w=30, bold_value=True)
    else:
        installment = round(balance / 4, 2)
        remainder = round(balance - installment * 3, 2)
        amounts = [installment, installment, installment, remainder]
        month_offsets = [1, 2, 3, 4]
        base_month = datetime.now().month
        base_year = datetime.now().year
        for idx, offset in enumerate(month_offsets):
            month = base_month + offset
            year = base_year
            while month > 12:
                month -= 12
                year += 1
            due_label = datetime(year, month, 10).strftime("%B %d, %Y")
            fin_row(right_x, ry + idx * row_step, due_label, _format_money(amounts[idx]), label_w=38)
        ry += row_step * 4
        fin_row(
            right_x,
            ry,
            "Total Outstanding Balance",
            _format_money(balance),
            label_w=38,
            bold_value=True,
        )

    fin_h = max(ly, ry) - fin_top + 3.0
    table_box(mx, fin_top, content_w, fin_h)
    hline(mx + col_w + col_gap / 2, fin_top, mx + col_w + col_gap / 2, fin_top + fin_h)

    bottom_margin = 5.0
    y = fin_top + fin_h + 3.0
    disclaimer = (
        "THIS IS A SYSTEM GENERATED ASSESSMENT. ANY ALTERATION BY THE SCHOOL OR ANY OTHER "
        "PARTY IS NOT AUTHORIZED AND MAY RENDER YOUR ENROLLMENT AND PAYMENT INVALID."
    )
    for line in textwrap.wrap(disclaimer, width=108):
        write_center(mx, y, content_w, line, size=5.5, color=muted)
        y += 2.4

    y += 1.2
    sig_line_y = y + 3.8
    hline(mx, sig_line_y, mx + 46, sig_line_y)
    write(mx, sig_line_y + 3.0, "REGISTRAR", size=6.5, bold=True)

    write_center(
        mx, sig_line_y + 1.2, content_w,
        "This is system-generated. Signature is not required.",
        size=6, color=muted,
    )
    write_center(
        mx, sig_line_y + 5.0, content_w,
        f"Official Registration Certificate — layout {COR_PDF_LAYOUT_VERSION}",
        size=5.5, color=muted,
    )

    footer_bottom = sig_line_y + 7.5
    if footer_bottom > page_h - bottom_margin:
        raise RuntimeError(
            f"Registration certificate footer exceeds page ({footer_bottom:.1f}mm > "
            f"{page_h - bottom_margin:.1f}mm). Reduce subject rows or financial height."
        )

    out = bytes(pdf.output())
    if len(re.findall(rb"/Type\s*/Page\b(?!s)", out)) != 1:
        raise RuntimeError("Registration certificate must fit on exactly one page.")
    return out


def save_registration_certificate_pdf(root: Path, data: dict, school_name: str) -> str:
    student_id = (
        data.get("studentId")
        or data.get("student_id_generated")
        or data.get("applicationNumber")
        or "student"
    )
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(student_id))
    out_dir = root / "uploads" / "registration-forms"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{safe_id}_Registration_Certificate.pdf"
    target = out_dir / filename
    target.write_bytes(build_registration_certificate_pdf(data, school_name))
    return str(target.relative_to(root)).replace("\\", "/")


def save_registration_form(root: Path, data: dict, school_name: str) -> str:
    """Save PDF certificate for email attachment and student portal download."""
    return save_registration_certificate_pdf(root, data, school_name)


def build_registration_certificate_email_attachment(
    result: dict,
    form_data: dict,
    school_name: str,
    root: Path,
    sibling_roots: list[Path] | None = None,
) -> dict:
    """Attach PDF registration certificate to approval email."""
    pdf_bytes = build_registration_certificate_pdf(form_data, school_name)
    if not pdf_bytes.startswith(b"%PDF"):
        raise RuntimeError("Registration certificate PDF generation failed (invalid output).")

    student_id = (
        result.get("studentId")
        or form_data.get("studentId")
        or form_data.get("applicationNumber")
        or "student"
    )
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(student_id))
    filename = f"{safe_id}_Registration_Certificate.pdf"
    out_dir = root / "uploads" / "registration-forms"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / filename
    target.write_bytes(pdf_bytes)
    result["registrationFormPath"] = str(target.relative_to(root)).replace("\\", "/")

    for extra in sibling_roots or []:
        if not extra.is_dir():
            continue
        sibling_dir = extra / "uploads" / "registration-forms"
        sibling_dir.mkdir(parents=True, exist_ok=True)
        (sibling_dir / filename).write_bytes(pdf_bytes)

    schedule_count = len(form_data.get("subjectScheduleDetails") or [])
    name = f"Registration_Certificate_{student_id}.pdf"
    print(
        f"[Registration certificate] layout={COR_PDF_LAYOUT_VERSION} {name} "
        f"({len(pdf_bytes)} bytes, {schedule_count} schedule row(s))"
    )
    return {
        "content": pdf_bytes,
        "name": name,
        "mime": "application/pdf",
    }


def write_registration_certificate_http(handler, pdf_bytes: bytes, student_id: str, *, inline: bool = True) -> None:
    """Stream a COR PDF over HTTP with no-cache headers."""
    disposition = "inline" if inline else "attachment"
    filename = f"Registration_Certificate_{student_id}.pdf"
    handler.send_response(200)
    handler.send_header("Content-Type", "application/pdf")
    handler.send_header("Content-Disposition", f'{disposition}; filename="{filename}"')
    handler.send_header("X-COR-Layout", COR_PDF_LAYOUT_VERSION)
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Content-Length", str(len(pdf_bytes)))
    handler.end_headers()
    handler.wfile.write(pdf_bytes)


def build_registration_certificate_for_student(
    student_id: str,
    school_name: str,
    *,
    admission_detail: dict | None,
    rest_get_fn=None,
) -> bytes | None:
    """Build a fresh COR PDF from an approved admission record."""
    if not admission_detail:
        return None

    result = {
        "status": "approved",
        "studentId": admission_detail.get("studentId") or student_id,
        "email": admission_detail.get("email"),
        "firstName": admission_detail.get("firstName"),
        "lastName": admission_detail.get("lastName"),
        "middleName": admission_detail.get("middleName"),
        "applicationNumber": admission_detail.get("applicationNumber"),
        "applicationId": admission_detail.get("id"),
        "gradeLevel": admission_detail.get("gradeLevel"),
        "strandCode": admission_detail.get("strandCode"),
        "address": admission_detail.get("address"),
        "contactNumber": admission_detail.get("contactNumber"),
        "schoolYear": admission_detail.get("schoolYear") or "2026-2027",
        "semester": admission_detail.get("semester") or "1st",
        "campus": admission_detail.get("campus") or "Main Campus",
    }
    form_data = prepare_form_data(result, admission_detail, rest_get_fn=rest_get_fn)
    pdf_bytes = build_registration_certificate_pdf(form_data, school_name)
    if not pdf_bytes.startswith(b"%PDF"):
        return None
    print(f"[COR] Generated layout {COR_PDF_LAYOUT_VERSION} for {student_id} ({len(pdf_bytes)} bytes)")
    return pdf_bytes
