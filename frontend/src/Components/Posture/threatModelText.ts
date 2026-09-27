// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// Wording for the curated threat-model questionnaire (21.4). The engine ships
// ids only; every language gets its prose from here. Literal keys (no
// template strings) so the i18n tooling can see every one. An id this file
// does not know falls back to the id itself -- never a blank.

import type { TFunction } from 'i18next';

interface QuestionText {
    title: string;
    why: string;
}

export const questionText = (t: TFunction, id: string): QuestionText => {
    const texts: Record<string, QuestionText> = {
        org: {
            title: t('threatModel.question.org.title', 'What best describes this installation?'),
            why: t('threatModel.question.org.why', 'It sets the baseline for how much assurance is reasonable.'),
        },
        data: {
            title: t('threatModel.question.data.title', 'What kinds of data do these systems hold or process?'),
            why: t('threatModel.question.data.why', 'Regulated data brings obligations that a generic baseline does not cover.'),
        },
        regs: {
            title: t('threatModel.question.regs.title', 'Which of these obligations apply to you?'),
            why: t('threatModel.question.regs.why', 'Each obligation adds specific controls, such as audit retention, MFA or FIPS.'),
        },
        fips: {
            title: t('threatModel.question.fips.title', 'Must cryptography be FIPS 140 validated?'),
            why: t('threatModel.question.fips.why', 'Federal and defense work often requires it, and it changes which hosts are compliant.'),
        },
        adversary: {
            title: t('threatModel.question.adversary.title', 'Who are you most concerned about?'),
            why: t('threatModel.question.adversary.why', 'Opportunistic attackers are stopped by good hygiene; targeted ones also need detection and response.'),
        },
        exposure: {
            title: t('threatModel.question.exposure.title', 'How reachable are these systems from the internet?'),
            why: t('threatModel.question.exposure.why', 'Exposure decides how much network hardening matters.'),
        },
        third_party: {
            title: t('threatModel.question.third_party.title', 'Do vendors or contractors have access?'),
            why: t('threatModel.question.third_party.why', 'Third-party access widens who holds credentials.'),
        },
        admins: {
            title: t('threatModel.question.admins.title', 'How many people administer these systems?'),
            why: t('threatModel.question.admins.why', 'More administrators means more accounts that must each be protected.'),
        },
        downtime: {
            title: t('threatModel.question.downtime.title', 'How long could these systems be down before it hurts?'),
            why: t('threatModel.question.downtime.why', 'A low tolerance calls for alerting and planned maintenance.'),
        },
        data_loss: {
            title: t('threatModel.question.data_loss.title', 'How much recent data could you afford to lose?'),
            why: t('threatModel.question.data_loss.why', 'This is your recovery point objective, and it decides what backups must achieve.'),
        },
        risk: {
            title: t('threatModel.question.risk.title', 'How much risk will you accept to save effort?'),
            why: t('threatModel.question.risk.why', 'It shapes which recommendations are worth their cost to you.'),
        },
    };
    return texts[id] ?? { title: id, why: '' };
};

export const optionText = (t: TFunction, questionId: string, optionId: string): string => {
    const texts: Record<string, Record<string, string>> = {
        org: {
            homelab: t('threatModel.option.org.homelab', 'A home lab or personal systems'),
            small_business: t('threatModel.option.org.small_business', 'A small business'),
            enterprise: t('threatModel.option.org.enterprise', 'An enterprise'),
            public_sector: t('threatModel.option.org.public_sector', 'The public sector or defense'),
        },
        data: {
            none_sensitive: t('threatModel.option.data.none_sensitive', 'Nothing sensitive'),
            personal: t('threatModel.option.data.personal', 'Personal information about people'),
            health: t('threatModel.option.data.health', 'Health information'),
            payment_cards: t('threatModel.option.data.payment_cards', 'Payment card data'),
            controlled_unclassified: t('threatModel.option.data.controlled_unclassified', 'Controlled unclassified information'),
            trade_secrets: t('threatModel.option.data.trade_secrets', 'Trade secrets or intellectual property'),
        },
        regs: {
            hipaa: t('threatModel.option.regs.hipaa', 'HIPAA'),
            pci_dss: t('threatModel.option.regs.pci_dss', 'PCI DSS'),
            gdpr: t('threatModel.option.regs.gdpr', 'GDPR'),
            cmmc_800_171: t('threatModel.option.regs.cmmc_800_171', 'CMMC / NIST SP 800-171'),
            none_known: t('threatModel.option.regs.none_known', 'None that I know of'),
        },
        fips: {
            yes: t('threatModel.option.fips.yes', 'Yes'),
            no: t('threatModel.option.fips.no', 'No'),
            unsure: t('threatModel.option.fips.unsure', 'I am not sure'),
        },
        adversary: {
            opportunistic: t('threatModel.option.adversary.opportunistic', 'Opportunistic attackers scanning the internet'),
            targeted_criminal: t('threatModel.option.adversary.targeted_criminal', 'Criminals targeting us specifically'),
            nation_state: t('threatModel.option.adversary.nation_state', 'Nation-state attackers'),
            insider: t('threatModel.option.adversary.insider', 'People inside the organization'),
        },
        exposure: {
            air_gapped: t('threatModel.option.exposure.air_gapped', 'Air-gapped: no network path to the internet'),
            internal_only: t('threatModel.option.exposure.internal_only', 'Internal only'),
            some_exposed: t('threatModel.option.exposure.some_exposed', 'Some systems are reachable from the internet'),
            widely_exposed: t('threatModel.option.exposure.widely_exposed', 'Many systems are reachable from the internet'),
        },
        third_party: {
            yes: t('threatModel.option.third_party.yes', 'Yes'),
            no: t('threatModel.option.third_party.no', 'No'),
        },
        admins: {
            one: t('threatModel.option.admins.one', 'Just one'),
            few: t('threatModel.option.admins.few', 'A few'),
            many: t('threatModel.option.admins.many', 'Many'),
        },
        downtime: {
            days: t('threatModel.option.downtime.days', 'Days'),
            hours: t('threatModel.option.downtime.hours', 'Hours'),
            minutes: t('threatModel.option.downtime.minutes', 'Minutes'),
        },
        data_loss: {
            a_week: t('threatModel.option.data_loss.a_week', 'About a week'),
            a_day: t('threatModel.option.data_loss.a_day', 'About a day'),
            minutes: t('threatModel.option.data_loss.minutes', 'Only minutes'),
        },
        risk: {
            low: t('threatModel.option.risk.low', 'As little as possible'),
            medium: t('threatModel.option.risk.medium', 'Some, where the effort is large'),
            high: t('threatModel.option.risk.high', 'Quite a lot'),
        },
    };
    return texts[questionId]?.[optionId] ?? optionId;
};

export const attributeText = (t: TFunction, id: string): string => {
    const texts: Record<string, string> = {
        regulated: t('threatModel.attribute.regulated', 'Handles regulated data'),
        phi: t('threatModel.attribute.phi', 'Handles health information'),
        pci: t('threatModel.attribute.pci', 'Handles payment card data'),
        cui: t('threatModel.attribute.cui', 'Handles controlled unclassified information'),
        fips_required: t('threatModel.attribute.fips_required', 'Requires FIPS-validated cryptography'),
        targeted: t('threatModel.attribute.targeted', 'Expects targeted attackers'),
        insider: t('threatModel.attribute.insider', 'Treats insiders as a threat'),
        internet_exposed: t('threatModel.attribute.internet_exposed', 'Reachable from the internet'),
        air_gapped: t('threatModel.attribute.air_gapped', 'Air-gapped'),
        third_party: t('threatModel.attribute.third_party', 'Vendors or contractors have access'),
        multi_admin: t('threatModel.attribute.multi_admin', 'Several administrators'),
        low_downtime_tolerance: t('threatModel.attribute.low_downtime_tolerance', 'Little tolerance for downtime'),
        low_data_loss_tolerance: t('threatModel.attribute.low_data_loss_tolerance', 'Little tolerance for data loss'),
        low_risk_tolerance: t('threatModel.attribute.low_risk_tolerance', 'Little tolerance for risk'),
    };
    return texts[id] ?? id;
};
