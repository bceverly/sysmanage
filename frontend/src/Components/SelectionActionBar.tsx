// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

/**
 * SelectionActionBar — one action bar for every grid in the product.
 *
 * WHY THIS EXISTS
 * ---------------
 * Screens grew to 5-13 bulk actions each and the button rows outgrew the
 * viewport.  The previous mitigation, ScrollableButtonBar, scrolled the
 * controls horizontally, which is the wrong trade: nothing tells you actions
 * are off-screen, there is no count of what is hidden, and panning a control
 * strip is awkward on a trackpad and worse on touch.
 *
 * The pattern here is what Gmail, GitHub, Linear, Drive, Fluent's CommandBar
 * and Salesforce Lightning all converge on, and what MUI X's own DataGrid
 * examples use:
 *
 *   1. CONTEXTUAL — the selection summary and Clear affordance appear only
 *      once something is selected.
 *   2. A SMALL PRIMARY SET plus a single overflow menu, and the overflow
 *      button CARRIES THE HIDDEN COUNT ("More · 4").  A hidden action nobody
 *      can count is the exact failure of the scrolling bar.
 *   3. GROUPED overflow with subheaders, destructive actions last behind a
 *      divider.
 *   4. DISABLED, NEVER HIDDEN, and always with a reason.  Hiding actions on
 *      selection change makes them undiscoverable and makes the bar's width
 *      jump.  ``disabledReason`` turns a dead grey control into an
 *      explanation — "Requires exactly one host", "Not supported on this
 *      agent" — which matters here because the gating is genuinely complex.
 *
 * The reason surface differs by control type on purpose.  A disabled MUI
 * Button swallows pointer events, so its tooltip needs a wrapper span; a
 * disabled MenuItem has the same problem AND wrapping it breaks the menu's
 * keyboard navigation.  So buttons get a tooltip and menu items render the
 * reason as inline secondary text, which needs no hover at all and is the
 * better affordance regardless.
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
    Box,
    Button,
    Chip,
    Divider,
    IconButton,
    ListItemIcon,
    ListItemText,
    ListSubheader,
    Menu,
    MenuItem,
    Tooltip,
    useMediaQuery,
    useTheme,
} from '@mui/material';
import MoreHorizIcon from '@mui/icons-material/MoreHoriz';
import CloseIcon from '@mui/icons-material/Close';
import { useTranslation } from 'react-i18next';

export type SelectionActionColor =
    | 'inherit'
    | 'primary'
    | 'secondary'
    | 'success'
    | 'error'
    | 'info'
    | 'warning';

export interface SelectionAction {
    /** Stable identity.  Used as the React key and as the test hook. */
    id: string;
    /** Already translated by the caller — screens own their own wording. */
    label: string;
    icon?: React.ReactNode;
    onClick: () => void;
    disabled?: boolean;
    /**
     * WHY it is disabled, in the operator's language.  Shown as a tooltip on a
     * primary button and as inline secondary text in the menu.  Strongly
     * recommended: a grey control with no explanation is a support ticket.
     */
    disabledReason?: string;
    /** Tooltip shown when the action is ENABLED. */
    tooltip?: string;
    /** Render in the always-visible row rather than the overflow menu. */
    primary?: boolean;
    /** Error colouring, sorted last, separated by a divider in the menu. */
    destructive?: boolean;
    /** Menu subheader to file this under.  Ungrouped items come first. */
    group?: string;
    color?: SelectionActionColor;
    /** Permission-gated away entirely.  Prefer `disabled` where it is merely
     *  unavailable — hidden actions cannot be discovered or explained. */
    hidden?: boolean;
}

export interface SelectionActionBarProps {
    actions: SelectionAction[];
    /** Rows currently selected.  0 hides the selection summary entirely. */
    selectionCount?: number;
    /** Renders the summary text.  Defaults to a generic "N selected". */
    selectionLabel?: (count: number) => string;
    onClearSelection?: () => void;
    /** Cap on the always-visible row at full width.  Default 4. */
    maxPrimary?: number;
    /**
     * Arbitrary nodes pinned to the primary row -- a screen that owns a
     * self-contained control (its own dialog trigger, a filter select) rather
     * than a plain action.  Never collapses into the overflow menu, so keep it
     * to one or two small things.
     */
    extras?: React.ReactNode;
    sx?: object;
}

const SelectionActionBar: React.FC<SelectionActionBarProps> = ({
    actions,
    selectionCount = 0,
    selectionLabel,
    onClearSelection,
    maxPrimary = 4,
    extras,
    sx,
}) => {
    const { t } = useTranslation();
    const theme = useTheme();
    // Two degradation steps, so the bar's HEIGHT never changes: full labels ->
    // icon-only primaries -> a single primary and everything else in the menu.
    // Wrapping to a second row would shift the grid above it on every resize.
    // Viewport breakpoints are only the FALLBACK.  They describe the window,
    // not this bar -- a 1400px window can still hand the bar an 1150px slot
    // inside a padded container, and the primaries then overrun the More
    // button and paint on top of it.  (Exactly that, caught in a screenshot
    // rather than by a test, is why the measurement below exists.)
    const viewportIconOnly = useMediaQuery(theme.breakpoints.down('lg'));
    const viewportVeryNarrow = useMediaQuery(theme.breakpoints.down('sm'));
    const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
    const barRef = useRef<HTMLDivElement | null>(null);
    const [barWidth, setBarWidth] = useState<number | null>(null);

    useEffect(() => {
        const el = barRef.current;
        // Absent in jsdom, so tests fall through to the viewport queries.
        if (!el || typeof ResizeObserver === 'undefined') {
            return undefined;
        }
        const observer = new ResizeObserver((entries) => {
            const width = entries[0]?.contentRect.width;
            if (typeof width === 'number') setBarWidth(width);
        });
        observer.observe(el);
        return () => observer.disconnect();
    }, []);

    const visible = useMemo(() => actions.filter((a) => !a.hidden), [actions]);

    // Deterministic step-downs rather than a fit-and-retry loop, which can
    // oscillate: removing a label frees space, which makes it fit, which puts
    // the label back.
    const APPROX_LABELLED_BUTTON = 200;
    const APPROX_ICON_BUTTON = 46;
    const APPROX_CHROME = 320; // selection chip + clear + More + gaps
    const primaryCandidateCount = useMemo(
        () => visible.filter((a) => a.primary).length,
        [visible],
    );
    const iconOnly =
        barWidth === null
            ? viewportIconOnly
            : barWidth < primaryCandidateCount * APPROX_LABELLED_BUTTON + APPROX_CHROME;
    const veryNarrow =
        barWidth === null
            ? viewportVeryNarrow
            : barWidth < APPROX_CHROME + APPROX_ICON_BUTTON * 2;

    const { primaryActions, menuActions } = useMemo(() => {
        const budget = veryNarrow ? 1 : maxPrimary;
        // Destructive actions are never promoted automatically; a caller that
        // really wants one up front marks it primary explicitly, and it is
        // sorted last so it is never adjacent to a benign action by accident.
        const candidates = visible
            .filter((a) => a.primary)
            .sort((a, b) => Number(!!a.destructive) - Number(!!b.destructive));
        const promoted = candidates.slice(0, budget);
        const promotedIds = new Set(promoted.map((a) => a.id));
        return {
            primaryActions: promoted,
            menuActions: visible.filter((a) => !promotedIds.has(a.id)),
        };
    }, [visible, maxPrimary, veryNarrow]);

    const groupedMenu = useMemo(() => {
        const groups = new Map<string, SelectionAction[]>();
        const ordered = [...menuActions].sort(
            (a, b) => Number(!!a.destructive) - Number(!!b.destructive),
        );
        ordered.forEach((action) => {
            const key = action.destructive
                ? ' destructive'
                : action.group || '';
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key)!.push(action);
        });
        return Array.from(groups.entries());
    }, [menuActions]);

    const closeMenu = () => setAnchorEl(null);

    const runAction = (action: SelectionAction) => {
        // A disabled MenuItem is only blocked by CSS pointer-events, not by a
        // real `disabled` attribute the way a Button is -- so anything that
        // dispatches a synthetic click (tests, automation, an extension) would
        // otherwise fire the handler.  Correctness should not depend on a
        // stylesheet.
        if (action.disabled) {
            return;
        }
        closeMenu();
        action.onClick();
    };

    // Composed from common.rowSelected / common.rowsSelected, which already
    // exist translated in all 15 locales -- a screen that wants its own noun
    // ("3 hosts selected") passes selectionLabel instead.
    const defaultSummary = (count: number) =>
        `${count} ${
            count === 1
                ? t('common.rowSelected', 'row selected')
                : t('common.rowsSelected', 'rows selected')
        }`;

    const summary =
        selectionCount > 0
            ? (selectionLabel || defaultSummary)(selectionCount)
            : '';

    const renderPrimary = (action: SelectionAction) => {
        const tip = action.disabled
            ? action.disabledReason || ''
            : action.tooltip || '';
        const control = iconOnly && action.icon ? (
            <IconButton
                aria-label={action.label}
                data-testid={`action-${action.id}`}
                color={action.color || (action.destructive ? 'error' : 'primary')}
                disabled={action.disabled}
                onClick={action.onClick}
                size="small"
                sx={{ border: 1, borderColor: 'divider', borderRadius: 1 }}
            >
                {action.icon}
            </IconButton>
        ) : (
            <Button
                variant="outlined"
                data-testid={`action-${action.id}`}
                startIcon={action.icon}
                color={action.color || (action.destructive ? 'error' : 'primary')}
                disabled={action.disabled}
                onClick={action.onClick}
                sx={{ whiteSpace: 'nowrap' }}
            >
                {action.label}
            </Button>
        );

        // A disabled MUI Button emits no pointer events, so the tooltip has to
        // hang off a wrapper that is still live.
        if (!tip) {
            return <Box key={action.id}>{control}</Box>;
        }
        return (
            <Tooltip key={action.id} title={tip}>
                <Box sx={{ display: 'inline-flex' }}>{control}</Box>
            </Tooltip>
        );
    };

    if (visible.length === 0 && !extras) {
        return null;
    }

    return (
        <Box
            ref={barRef}
            sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                flexWrap: 'nowrap',
                minHeight: 48,
                width: '100%',
                ...sx,
            }}
        >
            {selectionCount > 0 && (
                <Box
                    sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.5,
                        mr: 1,
                        flexShrink: 0,
                    }}
                >
                    <Chip
                        size="small"
                        color="primary"
                        label={summary}
                        data-testid="selection-summary"
                    />
                    {onClearSelection && (
                        <Tooltip title={t('common.clearSelection', 'Clear selection')}>
                            <IconButton
                                size="small"
                                aria-label={t('common.clearSelection', 'Clear selection')}
                                data-testid="selection-clear"
                                onClick={onClearSelection}
                            >
                                <CloseIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>
                    )}
                </Box>
            )}

            <Box
                sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                    flexGrow: 1,
                    flexShrink: 1,
                    minWidth: 0,
                    // Clip rather than overlap if the estimate above is ever
                    // wrong: a clipped button is recoverable, a button painted
                    // on top of another is not.
                    overflow: 'hidden',
                }}
            >
                {primaryActions.map(renderPrimary)}
                {extras}
            </Box>

            {menuActions.length > 0 && (
                <>
                    <Button
                        variant="outlined"
                        data-testid="selection-more"
                        aria-haspopup="menu"
                        aria-expanded={Boolean(anchorEl)}
                        startIcon={<MoreHorizIcon />}
                        onClick={(event) => setAnchorEl(event.currentTarget)}
                        sx={{ whiteSpace: 'nowrap', flexShrink: 0 }}
                    >
                        {t('common.moreActions', 'More')}
                        {` · ${menuActions.length}`}
                    </Button>
                    <Menu
                        anchorEl={anchorEl}
                        open={Boolean(anchorEl)}
                        onClose={closeMenu}
                        anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
                        transformOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                    >
                        {groupedMenu.flatMap(([groupKey, groupActions], groupIndex) => {
                            const nodes: React.ReactNode[] = [];
                            const isDestructive = groupKey === ' destructive';
                            if (groupIndex > 0) {
                                nodes.push(<Divider key={`div-${groupKey}`} />);
                            }
                            if (groupKey && !isDestructive) {
                                nodes.push(
                                    <ListSubheader key={`sub-${groupKey}`} disableSticky>
                                        {groupKey}
                                    </ListSubheader>,
                                );
                            }
                            groupActions.forEach((action: SelectionAction) => {
                                nodes.push(
                                    <MenuItem
                                        key={action.id}
                                        data-testid={`action-${action.id}`}
                                        disabled={action.disabled}
                                        onClick={() => runAction(action)}
                                        sx={
                                            action.destructive
                                                ? { color: 'error.main' }
                                                : undefined
                                        }
                                    >
                                        {action.icon && (
                                            <ListItemIcon
                                                sx={
                                                    action.destructive
                                                        ? { color: 'error.main' }
                                                        : undefined
                                                }
                                            >
                                                {action.icon}
                                            </ListItemIcon>
                                        )}
                                        <ListItemText
                                            primary={action.label}
                                            secondary={
                                                action.disabled && action.disabledReason
                                                    ? action.disabledReason
                                                    : undefined
                                            }
                                        />
                                    </MenuItem>,
                                );
                            });
                            return nodes;
                        })}
                    </Menu>
                </>
            )}
        </Box>
    );
};

export default SelectionActionBar;
export { SelectionActionBar };
