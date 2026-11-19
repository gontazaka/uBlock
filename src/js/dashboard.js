/*******************************************************************************

    uBlock Origin - a comprehensive, efficient content blocker
    Copyright (C) 2014-present Raymond Hill

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see {http://www.gnu.org/licenses/}.

    Home: https://github.com/gorhill/uBlock
*/

import { dom, qs$, qsa$ } from './dom.js';

/******************************************************************************/

function discardUnsavedData(synchronous = false) {
    const paneFrame = qs$('#iframe');
    const paneWindow = paneFrame.contentWindow;
    if (
        typeof paneWindow.hasUnsavedData !== 'function' ||
        paneWindow.hasUnsavedData() === false
    ) {
        return true;
    }

    if ( synchronous ) {
        return false;
    }

    return new Promise(resolve => {
        const modal = qs$('#unsavedWarning');
        dom.cl.add(modal, 'on');
        modal.focus();

        const onDone = status => {
            dom.cl.remove(modal, 'on');
            dom.off(document, 'click', onClick, true);
            resolve(status);
        };

        const onClick = ev => {
            const target = ev.target;
            if ( target.matches('[data-i18n="dashboardUnsavedWarningStay"]') ) {
                return onDone(false);
            }
            if ( target.matches('[data-i18n="dashboardUnsavedWarningIgnore"]') ) {
                return onDone(true);
            }
            if ( qs$(modal, '[data-i18n="dashboardUnsavedWarning"]').contains(target) ) {
                return;
            }
            onDone(false);
        };

        dom.on(document, 'click', onClick, true);
    });
}

function loadDashboardPanel(pane, first) {
    const tabButton = qs$(`[data-pane="${pane}"]`);
    if ( tabButton === null || dom.cl.has(tabButton, 'selected') ) { return; }
    const loadPane = ( ) => {
        self.location.replace(`#${pane}`);
        dom.cl.remove('.tabButton.selected', 'selected');
        dom.cl.add(tabButton, 'selected');
        tabButton.scrollIntoView();
        const iframe = qs$('#iframe');
        iframe.contentWindow.location.replace(pane);
        if ( pane !== 'no-dashboard.html' ) {
            iframe.addEventListener('load', ( ) => {
                qs$('.wikilink').href = iframe.contentWindow.wikilink || '';
            }, { once: true });
            vAPI.localStorage.setItem('dashboardLastVisitedPane', pane);
        }
    };
    if ( first ) {
        return loadPane();
    }
    const r = discardUnsavedData();
    if ( r === false ) { return; }
    if ( r === true ) { return loadPane(); }
    r.then(status => {
        if ( status === false ) { return; }
        loadPane();
    });
}

const SWIPE_EDGE_MARGIN = 24;
const SWIPE_LOCK_DISTANCE = 14;
const SWIPE_LOCK_RATIO = 2.0;
const SWIPE_COMMIT_ANGLE_RATIO = 1.8;
const SWIPE_FLICK_MIN_DISTANCE = 72;
const SWIPE_FLICK_MIN_VELOCITY = 0.45;
const SWIPE_FLICK_MAX_DURATION = 300;
const SWIPE_INDICATOR_HIDE_DELAY = 150;
const SWIPE_IGNORE_SELECTOR = [
    '.CodeMirror',
    'textarea',
    'select',
    '[contenteditable="true"]',
    'input:not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]):not([type="reset"])',
].join(',');

const swipeBoundDocs = new WeakSet();
let swipeIndicatorTimer;

function hideSwipeIndicator(immediate = true) {
    if ( swipeIndicatorTimer !== undefined ) {
        clearTimeout(swipeIndicatorTimer);
        swipeIndicatorTimer = undefined;
    }
    const indicator = qs$('#swipeIndicator');
    if ( indicator === null ) { return; }
    const clear = ( ) => {
        swipeIndicatorTimer = undefined;
        dom.cl.remove(indicator, 'visible', 'ready', 'dir-prev', 'dir-next');
    };
    if ( immediate ) {
        clear();
    } else {
        swipeIndicatorTimer = setTimeout(clear, SWIPE_INDICATOR_HIDE_DELAY);
    }
}

function showSwipeIndicator(delta, label, ready) {
    if ( swipeIndicatorTimer !== undefined ) {
        clearTimeout(swipeIndicatorTimer);
        swipeIndicatorTimer = undefined;
    }
    const indicator = qs$('#swipeIndicator');
    if ( indicator === null ) { return; }
    dom.text(qs$(indicator, '.swipe-label'), label);
    dom.cl.toggle(indicator, 'dir-prev', delta < 0);
    dom.cl.toggle(indicator, 'dir-next', delta > 0);
    dom.cl.add(indicator, 'visible');
    dom.cl.toggle(indicator, 'ready', ready);
}

function getAdjacentTab(delta) {
    const tabs = Array.from(qsa$('#dashboard-nav .tabButton'))
        .filter(btn => dom.attr(btn, 'data-pane') !== 'no-dashboard.html');
    const currentIndex = tabs.findIndex(btn => dom.cl.has(btn, 'selected'));
    if ( currentIndex === -1 ) { return null; }
    const nextIndex = currentIndex + delta;
    if ( nextIndex < 0 || nextIndex >= tabs.length ) { return null; }
    return tabs[nextIndex];
}

function getCommitDistance(viewportWidth) {
    return Math.max(96, Math.min(160, viewportWidth * 0.28));
}

function shouldIgnoreSwipeTarget(target, rootDoc) {
    const win = rootDoc.defaultView;
    if ( win === null || target === null ) { return true; }
    let el = target.nodeType === 3 ? target.parentElement : target;
    if ( el === null || typeof el.closest !== 'function' ) { return true; }
    if ( el.closest(SWIPE_IGNORE_SELECTOR) !== null ) {
        return true;
    }
    while ( el !== null && el !== rootDoc.documentElement && el !== rootDoc.body ) {
        if ( el.scrollWidth > el.clientWidth + 1 ) {
            const overflowX = win.getComputedStyle(el).overflowX;
            if ( overflowX === 'auto' || overflowX === 'scroll' ) {
                return true;
            }
        }
        el = el.parentElement;
    }
    return false;
}

function attachSwipeNavigation(iframe) {
    let doc;
    try {
        doc = iframe.contentDocument;
    } catch {
        return;
    }
    if ( doc === null || swipeBoundDocs.has(doc) ) { return; }
    const win = doc.defaultView;
    if ( win === null ) { return; }
    swipeBoundDocs.add(doc);

    let state = null;

    const reset = (immediate = true) => {
        state = null;
        hideSwipeIndicator(immediate);
    };

    const onTouchStart = ev => {
        if (
            dom.cl.has(dom.body, 'noDashboard') ||
            dom.cl.has('#unsavedWarning', 'on') ||
            ev.touches.length !== 1
        ) {
            reset();
            return;
        }
        if ( win.visualViewport && win.visualViewport.scale > 1.05 ) {
            reset();
            return;
        }
        const selection = win.getSelection();
        if ( selection && selection.isCollapsed === false && selection.toString().length > 0 ) {
            reset();
            return;
        }
        const touch = ev.touches[0];
        const viewportWidth = doc.documentElement.clientWidth || win.innerWidth || 0;
        if (
            viewportWidth <= SWIPE_EDGE_MARGIN * 2 ||
            touch.clientX <= SWIPE_EDGE_MARGIN ||
            touch.clientX >= viewportWidth - SWIPE_EDGE_MARGIN
        ) {
            reset();
            return;
        }
        if ( shouldIgnoreSwipeTarget(ev.target, doc) ) {
            reset();
            return;
        }
        state = {
            startX: touch.clientX,
            startY: touch.clientY,
            startTime: performance.now(),
            viewportWidth,
            axis: null,
        };
    };

    const onTouchMove = ev => {
        if ( state === null ) { return; }
        if ( ev.touches.length !== 1 ) {
            reset();
            return;
        }
        const touch = ev.touches[0];
        const dx = touch.clientX - state.startX;
        const dy = touch.clientY - state.startY;
        const absDx = Math.abs(dx);
        const absDy = Math.abs(dy);

        if ( state.axis === null ) {
            if ( Math.hypot(dx, dy) < SWIPE_LOCK_DISTANCE ) { return; }
            state.axis = absDx >= absDy * SWIPE_LOCK_RATIO ? 'x' : 'y';
        }
        if ( state.axis !== 'x' ) { return; }

        if ( absDx < SWIPE_LOCK_DISTANCE || absDx < absDy * SWIPE_COMMIT_ANGLE_RATIO ) {
            hideSwipeIndicator();
            return;
        }
        const delta = dx < 0 ? 1 : -1;
        const targetTab = getAdjacentTab(delta);
        if ( targetTab === null ) {
            hideSwipeIndicator();
            return;
        }
        const commitDist = getCommitDistance(state.viewportWidth);
        const ready = absDx >= commitDist;
        showSwipeIndicator(delta, dom.text(targetTab).trim(), ready);
    };

    const onTouchEnd = ev => {
        if ( state === null ) { return; }
        const current = state;
        state = null;
        if ( current.axis !== 'x' || ev.changedTouches.length === 0 ) {
            hideSwipeIndicator();
            return;
        }
        const touch = ev.changedTouches[0];
        const dx = touch.clientX - current.startX;
        const dy = touch.clientY - current.startY;
        const absDx = Math.abs(dx);
        const absDy = Math.abs(dy);
        const dt = Math.max(1, performance.now() - current.startTime);

        if ( absDx < absDy * SWIPE_COMMIT_ANGLE_RATIO ) {
            hideSwipeIndicator();
            return;
        }
        const delta = dx < 0 ? 1 : -1;
        const targetTab = getAdjacentTab(delta);
        if ( targetTab === null ) {
            hideSwipeIndicator();
            return;
        }
        const commitDist = getCommitDistance(current.viewportWidth);
        const isDistanceCommit = absDx >= commitDist;
        const isFlickCommit =
            absDx >= SWIPE_FLICK_MIN_DISTANCE &&
            dt <= SWIPE_FLICK_MAX_DURATION &&
            (absDx / dt) >= SWIPE_FLICK_MIN_VELOCITY;

        if ( isDistanceCommit === false && isFlickCommit === false ) {
            hideSwipeIndicator();
            return;
        }
        showSwipeIndicator(delta, dom.text(targetTab).trim(), true);
        hideSwipeIndicator(false);
        loadDashboardPanel(dom.attr(targetTab, 'data-pane'));
    };

    const onTouchCancel = ( ) => {
        reset();
    };

    doc.addEventListener('touchstart', onTouchStart, { passive: true });
    doc.addEventListener('touchmove', onTouchMove, { passive: true });
    doc.addEventListener('touchend', onTouchEnd, { passive: true });
    doc.addEventListener('touchcancel', onTouchCancel, { passive: true });
}

function onTabClickHandler(ev) {
    loadDashboardPanel(dom.attr(ev.target, 'data-pane'));
}

if ( self.location.hash.slice(1) === 'no-dashboard.html' ) {
    dom.cl.add(dom.body, 'noDashboard');
}

(async ( ) => {
    // Wait for uBO's main process to be ready
    await new Promise(resolve => {
        const check = async ( ) => {
            try {
                const response = await vAPI.messaging.send('dashboard', {
                    what: 'readyToFilter'
                });
                if ( response ) { return resolve(true); }
                const iframe = qs$('#iframe');
                if ( iframe.src !== '' ) {
                    iframe.src = '';
                }
            } catch {
            }
            vAPI.defer.once(250).then(( ) => check());
        };
        check();
    });

    dom.cl.remove(dom.body, 'notReady');

    const results = await Promise.all([
        // https://github.com/uBlockOrigin/uBlock-issues/issues/106
        vAPI.messaging.send('dashboard', { what: 'dashboardConfig' }),
        vAPI.localStorage.getItemAsync('dashboardLastVisitedPane'),
    ]);

    {
        const details = results[0] || {};
        if ( details.noDashboard ) {
            self.location.hash = '#no-dashboard.html';
            dom.cl.add(dom.body, 'noDashboard');
        } else if ( self.location.hash === '#no-dashboard.html' ) {
            self.location.hash = '';
        }
    }

    {
        const iframe = qs$('#iframe');
        iframe.addEventListener('load', ( ) => {
            attachSwipeNavigation(iframe);
        });

        let pane = results[1] || null;
        if ( self.location.hash !== '' ) {
            pane = self.location.hash.slice(1) || null;
        }
        loadDashboardPanel(pane !== null ? pane : 'settings.html', true);

        dom.on('.tabButton', 'click', onTabClickHandler);

        // https://developer.mozilla.org/en-US/docs/Web/API/Window/beforeunload_event
        dom.on(self, 'beforeunload', ( ) => {
            if ( discardUnsavedData(true) ) { return; }
            event.preventDefault();
            event.returnValue = '';
        });

        // https://developer.mozilla.org/en-US/docs/Web/API/Window/beforeunload_event
        dom.on(self, 'hashchange', ( ) => {
            const pane = self.location.hash.slice(1);
            if ( pane === '' ) { return; }
            loadDashboardPanel(pane);
        });

    }
})();
