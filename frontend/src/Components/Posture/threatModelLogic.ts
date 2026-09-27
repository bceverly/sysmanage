// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

// The wizard's branching, mirroring advisor_engine's derive_threat_model so
// the operator sees exactly the questions the engine will derive from:
// `show_if` looks only BACK, and visibility CASCADES (a hidden question's
// answer is invisible to the questions after it). The server still derives
// the model -- this only decides what to ask.

import type { Answers, Question, Questionnaire } from '../../Services/postureService';

const chosen = (answer: string | string[] | undefined): string[] => {
    if (answer === undefined) return [];
    return Array.isArray(answer) ? answer : [answer];
};

export const questionVisible = (question: Question, effective: Answers): boolean => {
    const cond = question.show_if;
    if (!cond) return true;
    const [kind, refs] = Object.entries(cond)[0];
    const hit = Object.entries(refs).some(([qid, options]) =>
        chosen(effective[qid]).some(v => options.includes(v)));
    return kind === 'any_of' ? hit : !hit;
};

/** The questions shown for these answers, in order. */
export const visibleQuestions = (questionnaire: Questionnaire, answers: Answers): Question[] => {
    const effective: Answers = {};
    const shown: Question[] = [];
    for (const question of questionnaire.questions) {
        if (questionVisible(question, effective)) {
            shown.push(question);
            if (answers[question.id] !== undefined) effective[question.id] = answers[question.id];
        }
    }
    return shown;
};

export const isAnswered = (question: Question, answers: Answers): boolean =>
    chosen(answers[question.id]).length > 0;

/** Only the answers to visible questions: what is saved. A branch the
 *  operator closed must not carry its old answer into the model. */
export const visibleAnswers = (questionnaire: Questionnaire, answers: Answers): Answers => {
    const out: Answers = {};
    for (const question of visibleQuestions(questionnaire, answers)) {
        if (isAnswered(question, answers)) out[question.id] = answers[question.id];
    }
    return out;
};
