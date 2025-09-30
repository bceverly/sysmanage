#!/usr/bin/env python3
"""
Update translation files with missing keys for Grafana/OpenTelemetry/Prometheus.
"""
import json
import os
from pathlib import Path

LOCALES_DIR = Path("/home/bceverly/dev/sysmanage/frontend/public/locales")

# Translation data for each language
TRANSLATIONS = {
    "en": {
        "common": {
            "active": "Active",
            "inactive": "Inactive",
            "enabled": "Enabled",
            "disabled": "Disabled",
            "running": "Running",
            "stopped": "Stopped",
            "refresh": "Refresh"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "Requests",
                "logging": "Logging"
            }
        }
    },
    "ar": {
        "common": {
            "active": "نشط",
            "inactive": "غير نشط",
            "enabled": "ممكّن",
            "disabled": "معطل",
            "running": "قيد التشغيل",
            "stopped": "متوقف",
            "refresh": "تحديث"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "الطلبات",
                "logging": "التسجيل"
            }
        }
    },
    "de": {
        "common": {
            "active": "Aktiv",
            "inactive": "Inaktiv",
            "enabled": "Aktiviert",
            "disabled": "Deaktiviert",
            "running": "Läuft",
            "stopped": "Gestoppt",
            "refresh": "Aktualisieren"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "Anfragen",
                "logging": "Protokollierung"
            }
        }
    },
    "es": {
        "common": {
            "active": "Activo",
            "inactive": "Inactivo",
            "enabled": "Habilitado",
            "disabled": "Deshabilitado",
            "running": "En ejecución",
            "stopped": "Detenido",
            "refresh": "Actualizar"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "Solicitudes",
                "logging": "Registro"
            }
        }
    },
    "fr": {
        "common": {
            "active": "Actif",
            "inactive": "Inactif",
            "enabled": "Activé",
            "disabled": "Désactivé",
            "running": "En cours d'exécution",
            "stopped": "Arrêté",
            "refresh": "Actualiser"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "Requêtes",
                "logging": "Journalisation"
            }
        }
    },
    "hi": {
        "common": {
            "active": "सक्रिय",
            "inactive": "निष्क्रिय",
            "enabled": "सक्षम",
            "disabled": "अक्षम",
            "running": "चल रहा है",
            "stopped": "रुका हुआ",
            "refresh": "रीफ़्रेश करें"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "अनुरोध",
                "logging": "लॉगिंग"
            }
        }
    },
    "it": {
        "common": {
            "active": "Attivo",
            "inactive": "Inattivo",
            "enabled": "Abilitato",
            "disabled": "Disabilitato",
            "running": "In esecuzione",
            "stopped": "Fermato",
            "refresh": "Aggiorna"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "Richieste",
                "logging": "Registrazione"
            }
        }
    },
    "ja": {
        "common": {
            "active": "アクティブ",
            "inactive": "非アクティブ",
            "enabled": "有効",
            "disabled": "無効",
            "running": "実行中",
            "stopped": "停止",
            "refresh": "更新"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "リクエスト",
                "logging": "ロギング"
            }
        }
    },
    "ko": {
        "common": {
            "active": "활성",
            "inactive": "비활성",
            "enabled": "활성화됨",
            "disabled": "비활성화됨",
            "running": "실행 중",
            "stopped": "중지됨",
            "refresh": "새로고침"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "요청",
                "logging": "로깅"
            }
        }
    },
    "nl": {
        "common": {
            "active": "Actief",
            "inactive": "Inactief",
            "enabled": "Ingeschakeld",
            "disabled": "Uitgeschakeld",
            "running": "Actief",
            "stopped": "Gestopt",
            "refresh": "Vernieuwen"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "Verzoeken",
                "logging": "Logboekregistratie"
            }
        }
    },
    "pt": {
        "common": {
            "active": "Ativo",
            "inactive": "Inativo",
            "enabled": "Ativado",
            "disabled": "Desativado",
            "running": "Em execução",
            "stopped": "Parado",
            "refresh": "Atualizar"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "Solicitações",
                "logging": "Registro"
            }
        }
    },
    "ru": {
        "common": {
            "active": "Активный",
            "inactive": "Неактивный",
            "enabled": "Включено",
            "disabled": "Отключено",
            "running": "Работает",
            "stopped": "Остановлено",
            "refresh": "Обновить"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "Запросы",
                "logging": "Журналирование"
            }
        }
    },
    "zh_CN": {
        "common": {
            "active": "活跃",
            "inactive": "不活跃",
            "enabled": "已启用",
            "disabled": "已禁用",
            "running": "运行中",
            "stopped": "已停止",
            "refresh": "刷新"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "请求",
                "logging": "日志记录"
            }
        }
    },
    "zh_TW": {
        "common": {
            "active": "活躍",
            "inactive": "不活躍",
            "enabled": "已啟用",
            "disabled": "已禁用",
            "running": "執行中",
            "stopped": "已停止",
            "refresh": "重新整理"
        },
        "telemetry": {
            "instrumentation": {
                "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy",
                "requests": "請求",
                "logging": "日誌記錄"
            }
        }
    }
}


def deep_merge(base, updates):
    """Recursively merge updates into base dictionary."""
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        elif key not in base:
            base[key] = value
    return base


def update_translation_file(lang_code):
    """Update translation file for given language."""
    file_path = LOCALES_DIR / lang_code / "translation.json"

    if not file_path.exists():
        print(f"Warning: {file_path} does not exist, skipping")
        return

    # Read existing translations
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Get translations for this language
    if lang_code not in TRANSLATIONS:
        print(f"Warning: No translations defined for {lang_code}, skipping")
        return

    updates = TRANSLATIONS[lang_code]

    # Merge updates into existing data
    original_data = json.dumps(data, ensure_ascii=False, sort_keys=True)
    deep_merge(data, updates)
    new_data = json.dumps(data, ensure_ascii=False, sort_keys=True)

    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')  # Add newline at end of file

    if original_data != new_data:
        print(f"✓ Updated {lang_code}/translation.json")
    else:
        print(f"  {lang_code}/translation.json already up to date")


def main():
    """Update all translation files."""
    print("Updating translation files...")
    print()

    for lang_code in TRANSLATIONS.keys():
        update_translation_file(lang_code)

    print()
    print("Translation update complete!")


if __name__ == "__main__":
    main()