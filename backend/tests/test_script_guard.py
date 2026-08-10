import pytest
from app.services.script_guard import UnsupportedScriptError, detect_unsupported_script, validate_script


def test_latin_english_passes():
    text = "Experienced Senior Software Engineer with 8+ years building distributed cloud microservices."
    assert detect_unsupported_script(text) is None
    validate_script(text)  # Should not raise


def test_accented_latin_passes():
    text = "Work history: Senior Consultant in Zürich and São Paulo. Managed José and Müller at Nestlé."
    assert detect_unsupported_script(text) is None
    validate_script(text)  # Should not raise; accented Latin is explicitly allowed


def test_cyrillic_refused():
    text = "Резюме разработчика программного обеспечения. Опыт работы 5 лет в IT."
    assert detect_unsupported_script(text) == "Cyrillic"
    with pytest.raises(UnsupportedScriptError) as exc_info:
        validate_script(text, source_label="resume")
    assert "Cyrillic" in str(exc_info.value)
    assert "accented Latin" in str(exc_info.value)


def test_cjk_refused():
    text = "高级软件工程师 具备 8 年 Python 和 Java 开发经验 负责分布式系统架构设计"
    assert detect_unsupported_script(text) == "CJK"
    with pytest.raises(UnsupportedScriptError) as exc_info:
        validate_script(text, source_label="job description")
    assert "CJK" in str(exc_info.value)


def test_hebrew_refused():
    text = "קורות חיים מפתח תוכנה בכיר עם ניסיון רב בפיתוח מערכות"
    assert detect_unsupported_script(text) == "Hebrew"
    with pytest.raises(UnsupportedScriptError):
        validate_script(text)


def test_arabic_refused():
    text = "سيرة ذاتية مهندس برمجيات خبرة في تطوير التطبيقات والأنظمة"
    assert detect_unsupported_script(text) == "Arabic"
    with pytest.raises(UnsupportedScriptError):
        validate_script(text)


def test_devanagari_refused():
    text = "बायोडाटा वरिष्ठ सॉफ्टवेयर इंजीनियर 5 वर्षों का अनुभव"
    assert detect_unsupported_script(text) == "Devanagari"
    with pytest.raises(UnsupportedScriptError):
        validate_script(text)


def test_thai_refused():
    text = "ประวัติการทำงาน วิศวกรซอฟต์แวร์ ประสบการณ์ 5 ปี"
    assert detect_unsupported_script(text) == "Thai"
    with pytest.raises(UnsupportedScriptError):
        validate_script(text)


def test_ds_resume_with_greek_math_notation_passes():
    text = (
        "Data Scientist & Quantitative Engineer. Developed machine learning models for risk analysis. "
        "Estimated parameters alpha, beta, and theta using Maximum Likelihood Estimation (MLE). "
        "Calculated standard error sigma and confidence intervals with significance level alpha = 0.05. "
        "Formulated optimization problems with constraint lambda and regularization penalty mu. "
        "Evaluated model drift using Delta loss metrics across large datasets."
    )
    assert detect_unsupported_script(text) is None
    validate_script(text)  # Greek math terms in English text must pass cleanly


def test_mostly_latin_with_scattered_symbols_below_ratio_passes():
    # Long English resume (800+ Latin characters) with 10 Cyrillic characters (ratio ~1.2% < 10% threshold)
    text = (
        "Senior Data Infrastructure Engineer with 10+ years of experience leading cross-functional teams "
        "in building scalable data pipelines, streaming analytics platforms, and machine learning infrastructure. "
        "Architected distributed ETL pipelines using Apache Spark, Kafka, and Snowflake processing over 50TB daily. "
        "Optimized PostgreSQL query performance, reducing tail latency by 45% across core database microservices. "
        "Collaborated with international engineering teams including contacts in Москва and СПб for localized telemetry. "
        "Designed feature store architecture using Redis and Feast to support real-time model inference at 10k QPS. "
        "Led team of 12 software engineers, mentoring junior developers and driving technical design reviews. "
        "Published technical documentation, automated CI/CD deployment workflows with GitHub Actions and Terraform, "
        "and established comprehensive observability dashboards using Prometheus and Grafana."
    )
    assert detect_unsupported_script(text) is None
    validate_script(text)  # Should pass because ratio is well below 10% threshold

