# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Content-lifecycle federated site sync (Phase 16, Slice 7b).

Two halves of the byte-transport, both best-effort so they never break the
promotion they hang off:

* COORDINATOR — ``announce_promotion_to_sites``: on promotion into a subscribed
  environment, enqueue a ``content_view_sync`` federation command to each
  subscribed site carrying the coordinator's serve URL + version metadata.  The
  existing federation push worker delivers it to the site's command inbox.

* SITE — ``handle_content_view_sync``: called from the OSS
  ``federation_actuation_service.fanout_queued_commands`` when a
  ``content_view_sync`` command surfaces; dispatches an HTTP-pull plan to the
  site's mirror host so it fetches the version's bytes and serves them locally.
  The pull result flips the received-command COMPLETE/FAILED (which the site's
  report-back worker then acks upstream).
"""

import json
import logging

from backend.licensing.module_loader import module_loader
from backend.persistence import models

logger = logging.getLogger(__name__)

CV_SYNC_COMMAND = "content_view_sync"


def announce_promotion_to_sites(cv, to_env, version, shared_db, tenant_db) -> None:
    """Coordinator side: announce a just-promoted CVV to every site subscribed to
    ``to_env``.  No-op off a coordinator or with no subscriptions."""
    from backend.services.server_config_service import (
        get_federation_role,
    )  # noqa: PLC0415

    if get_federation_role() != "coordinator":
        return
    subs = (
        tenant_db.query(models.EnvironmentSiteSubscription)
        .filter(models.EnvironmentSiteSubscription.environment_id == to_env.id)
        .all()
    )
    if not subs:
        return

    from backend.api.content_lifecycle import (
        _host_fqdn,  # noqa: PLC0415
        _resolve_cv_serving_host,
    )

    try:
        host_id = _resolve_cv_serving_host(cv, shared_db, tenant_db)[0]
        fqdn = _host_fqdn(tenant_db, host_id)
    except Exception:  # noqa: BLE001 - announce is best-effort
        logger.warning(
            "content_lifecycle: cannot resolve serve URL for cv %s; not announcing",
            cv.id,
            exc_info=True,
        )
        return
    if not fqdn:
        return
    source_url = (
        f"http://{fqdn}/content-views/{cv.id}/{to_env.name}"  # NOSONAR LAN HTTP
    )
    params = {
        "cv_id": str(cv.id),
        "cv_name": cv.name,
        "version": version,
        "env_name": to_env.name,
        "source_url": source_url,
    }

    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from backend.persistence import db as db_module  # noqa: PLC0415
    from backend.services.federation_dispatch_service import (
        dispatch_command,
    )  # noqa: PLC0415

    main = sessionmaker(bind=db_module.get_engine())()
    try:
        for sub in subs:
            try:
                dispatch_command(
                    main,
                    command_type=CV_SYNC_COMMAND,
                    target_site_id=str(sub.site_id),
                    parameters=params,
                )
            except Exception:  # noqa: BLE001 - one bad site never blocks the rest
                logger.warning(
                    "content_lifecycle: announce to site %s failed",
                    sub.site_id,
                    exc_info=True,
                )
        main.commit()
    finally:
        main.close()


def handle_content_view_sync(session, cmd) -> None:
    """Site side: turn a received ``content_view_sync`` command into an HTTP-pull
    plan on the site's mirror host.  Owns the command's FSM: marks it FAILED on a
    bad payload / missing infra, else IN_PROGRESS after dispatching the pull (the
    pull result flips it COMPLETE/FAILED)."""
    from backend.services import federation_inbox_service as inbox  # noqa: PLC0415

    def _fail(reason):
        inbox.update_command_status(
            session,
            cmd.id,
            new_status=inbox.CMD_STATUS_FAILED,
            result={"error": reason},
        )

    try:
        params = json.loads(cmd.parameters_json or "{}")
    except (ValueError, TypeError):
        params = {}
    cv_id = params.get("cv_id")
    env_name = params.get("env_name")
    version = int(params.get("version") or 0)
    source_url = params.get("source_url")
    if not (cv_id and env_name and version and source_url):
        _fail("incomplete content_view_sync parameters")
        return

    engine = module_loader.get_module("content_lifecycle_engine")
    if engine is None:
        _fail("content_lifecycle_engine not loaded on this site")
        return
    settings = session.query(models.MirrorSettings).first()
    mirror = (
        session.query(models.MirrorRepository)
        .filter(models.MirrorRepository.host_id.isnot(None))
        .first()
    )
    if settings is None or mirror is None:
        _fail("site has no mirror host to receive content")
        return

    plan = engine.build_pull_content_plan(
        source_url, settings.mirror_root_path, cv_id, env_name, version
    )
    from backend.services.proplus_dispatch import (  # noqa: PLC0415
        enqueue_apply_plan,
        register_content_lifecycle_correlation,
    )

    msg_id = enqueue_apply_plan(host_id=str(mirror.host_id), plan=plan, timeout=7200)
    register_content_lifecycle_correlation(
        msg_id, "cv_pull", str(mirror.host_id), str(cmd.id)
    )
    inbox.update_command_status(
        session, cmd.id, new_status=inbox.CMD_STATUS_IN_PROGRESS
    )
    logger.info(
        "content_lifecycle: site pulling cv=%s env=%s v%s from %s (host %s)",
        cv_id,
        env_name,
        version,
        source_url,
        mirror.host_id,
    )
