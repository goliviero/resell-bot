// ==UserScript==
// @name         Resell-Bot AutoBuy
// @namespace    resell-bot
// @version      1.10
// @description  Auto add-to-cart + checkout quand l'URL contient ?autobuy=1 (RecycLivre + Momox)
// @match        https://www.recyclivre.com/*
// @match        https://www.momox-shop.fr/*
// @match        https://momox-shop.fr/*
// @grant        GM_info
// @run-at       document-start
// ==/UserScript==

(function () {
    'use strict';

    console.log('[AutoBuy] Script v1.10 loaded on', window.location.hostname, 'url:', window.location.href);

    // Detect autobuy trigger via hash: #autobuy=<path> (relay via homepage) or #autobuy (direct)
    const hash = window.location.hash;
    const url = new URL(window.location.href);

    if (hash.startsWith('#autobuy=')) {
        // Relay mode: bot opened homepage with #autobuy=/path/to/product.html
        // Set sessionStorage, then navigate to the product page
        const targetPath = decodeURIComponent(hash.substring('#autobuy='.length));
        console.log('[AutoBuy] Relay mode — setting flag, navigating to:', targetPath);
        sessionStorage.setItem('resell_autobuy', '1');
        window.location.href = targetPath;
        return;
    }

    if (hash === '#autobuy' || url.searchParams.has('autobuy')) {
        console.log('[AutoBuy] Direct trigger detected, activating');
        sessionStorage.setItem('resell_autobuy', '1');
        url.searchParams.delete('autobuy');
        url.hash = '';
        try { (unsafeWindow || window).history.replaceState({}, '', url.toString()); } catch(e) {}
    }

    const autobuyActive = sessionStorage.getItem('resell_autobuy') === '1';
    if (!autobuyActive) {
        console.log('[AutoBuy] Not active, exiting');
        return;
    }

    console.log('[AutoBuy] Active! Waiting for DOM...');

    // Wait for DOM to be ready before interacting with page elements
    function onReady(fn) {
        if (document.readyState === 'complete' || document.readyState === 'interactive') {
            setTimeout(fn, 100);
        } else {
            document.addEventListener('DOMContentLoaded', fn);
        }
    }

    onReady(function () {
        console.log('[AutoBuy] DOM ready, processing', window.location.pathname);
        runAutoBuy();
    });

    // ── Helpers ────────────────────────────────────────────────

    function isVisible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        let p = el.parentElement;
        while (p) {
            const ps = window.getComputedStyle(p);
            if (ps.display === 'none') return false;
            p = p.parentElement;
        }
        return true;
    }

    function findVisibleByText(text) {
        const all = document.querySelectorAll('a, button');
        for (const el of all) {
            if (el.textContent.trim().toLowerCase().includes(text.toLowerCase()) && isVisible(el)) {
                return el;
            }
        }
        return null;
    }

    function waitClickAny(selectors, timeout = 10000) {
        return new Promise((resolve, reject) => {
            const start = Date.now();
            function check() {
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && isVisible(el)) {
                        console.log('[AutoBuy] Click:', sel, el.textContent.trim().slice(0, 40));
                        el.click();
                        resolve(el);
                        return;
                    }
                }
                if (Date.now() - start > timeout) {
                    reject(new Error('[AutoBuy] Timeout: ' + selectors.join(', ')));
                    return;
                }
                setTimeout(check, 300);
            }
            check();
        });
    }

    function sleep(ms) {
        return new Promise(r => setTimeout(r, ms));
    }

    function showBanner(text) {
        const banner = document.createElement('div');
        banner.textContent = '\u26A1 ' + text;
        banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;background:#22c55e;color:white;text-align:center;padding:10px;font-weight:bold;font-size:14px;font-family:sans-serif;box-shadow:0 2px 8px rgba(0,0,0,0.3);';
        document.body.appendChild(banner);
        setTimeout(() => banner.remove(), 4000);
    }

    // ── Main logic (called after DOM ready) ───────────────────

    function runAutoBuy() {
        // ── RecycLivre ──────────────────────────────────────────
        if (window.location.hostname.includes('recyclivre.com')) {
            const path = window.location.pathname;

            if (path.startsWith('/products/') && !path.includes('carte-cadeau')) {
                (async () => {
                    showBanner('AutoBuy: ajout au panier...');
                    try {
                        await sleep(1500);
                        await waitClickAny([
                            'button[onclick="clickToTheRightButton()"]',
                            'button.btn-primary-darker.w-full',
                            '#sylius-product-adding-to-cart button.btn-primary-darker',
                        ]);

                        showBanner('AutoBuy: article ajoute ! Redirection vers le panier...');
                        await sleep(2000);

                        try {
                            await waitClickAny([
                                'a[href="/cart/"].btn-primary',
                                'a[href="/cart"].btn-primary-darker',
                                'a[href="/cart/"].btn',
                                'a[href="/cart"].btn',
                            ], 5000);
                        } catch (e) {
                            console.log('[AutoBuy] Modal not found, navigating to cart');
                            window.location.href = '/cart/';
                        }
                    } catch (e) {
                        console.warn(e.message);
                        showBanner('AutoBuy: bouton non trouve, verifie la page');
                    }
                })();
                return;
            }

            if (path === '/cart' || path === '/cart/') {
                (async () => {
                    showBanner('AutoBuy: validation du panier...');
                    try {
                        await sleep(1500);
                        await waitClickAny([
                            'a[href="/checkout"]',
                            'a[href="/checkout/"]',
                            'a[href*="checkout"].btn',
                        ]);
                    } catch (e) {
                        console.warn(e.message);
                        showBanner('AutoBuy: bouton Valider non trouve');
                    }
                })();
                return;
            }

            if (path.startsWith('/checkout')) {
                sessionStorage.removeItem('resell_autobuy');
                showBanner('AutoBuy: checkout atteint ! Complete le paiement.');
                return;
            }
        }

        // ── Momox Shop ──────────────────────────────────────────
        if (window.location.hostname.includes('momox-shop.fr')) {
            const path = window.location.pathname;

            // Product page (*.html) — add to cart
            if (path.endsWith('.html') && !path.includes('Panier') && !path.includes('Donnees') && !path.includes('Paiement') && !path.includes('Confirmation')) {
                (async () => {
                    showBanner('AutoBuy: ajout au panier...');
                    try {
                        await sleep(1500);
                        // Accept cookies if present
                        try {
                            const cookieBtn = document.querySelector('[data-testid="uc-accept-all-button"], .uc-accept-all-button');
                            if (cookieBtn) { cookieBtn.click(); await sleep(1000); }
                        } catch(e) {}

                        await waitClickAny([
                            'button[data-cnstrc-btn="add_to_cart"][aria-label="buy"]',
                            'button[data-cnstrc-btn="add_to_cart"]',
                            'button[aria-label="buy"]',
                        ]);

                        showBanner('AutoBuy: article ajoute ! Passage en caisse...');
                        await sleep(2500);

                        try {
                            await waitClickAny([
                                'a[href*="/Panier"]',
                            ], 3000);
                        } catch (e) {
                            const btn = findVisibleByText('Passer');
                            if (btn) {
                                console.log('[AutoBuy] Found by text:', btn.textContent.trim());
                                btn.click();
                            } else {
                                console.log('[AutoBuy] Flyout not found, navigating to cart');
                                window.location.href = '/Panier/';
                            }
                        }
                    } catch (e) {
                        console.warn(e.message);
                        showBanner('AutoBuy: bouton non trouve');
                        window.location.href = '/Panier/';
                    }
                })();
                return;
            }

            // Cart /Panier/
            if (path.includes('Panier')) {
                (async () => {
                    showBanner('AutoBuy: passage en caisse...');
                    try {
                        await sleep(1500);
                        await waitClickAny([
                            'button.cart-page__checkout-button',
                            'button[href*="Donnees-Personnelles"]',
                            'a[href*="Donnees-Personnelles"]',
                        ], 8000);
                    } catch (e) {
                        const btn = findVisibleByText('Passer');
                        if (btn) btn.click();
                        else console.warn('[AutoBuy] Checkout button not found in cart');
                    }
                })();
                return;
            }

            // Shipping /Donnees-Personnelles/
            if (path.includes('Donnees-Personnelles')) {
                (async () => {
                    showBanner('AutoBuy: confirmation livraison...');
                    try {
                        await sleep(2000);
                        await waitClickAny([
                            'button[type="submit"]',
                            'input[type="submit"]',
                        ], 5000);
                    } catch (e) {
                        const btn = findVisibleByText('Continuer') || findVisibleByText('Weiter');
                        if (btn) btn.click();
                    }
                })();
                return;
            }

            // Payment /Paiement/
            if (path.includes('Paiement')) {
                (async () => {
                    showBanner('AutoBuy: selection paiement...');
                    try {
                        await sleep(2000);
                        await waitClickAny([
                            'button[type="submit"]',
                            'input[type="submit"]',
                        ], 5000);
                    } catch (e) {
                        const btn = findVisibleByText('Continuer') || findVisibleByText('Weiter');
                        if (btn) btn.click();
                    }
                    sessionStorage.removeItem('resell_autobuy');
                    showBanner('AutoBuy: page de paiement atteinte !');
                })();
                return;
            }

            // Confirmation
            if (path.includes('Confirmation')) {
                sessionStorage.removeItem('resell_autobuy');
                showBanner('AutoBuy: commande confirmee !');
                return;
            }
        }
    }
})();
