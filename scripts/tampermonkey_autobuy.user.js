// ==UserScript==
// @name         Resell-Bot AutoBuy
// @namespace    resell-bot
// @version      2.1
// @description  Auto add-to-cart + checkout quand l'URL contient #autobuy (RecycLivre + Momox)
// @match        https://www.recyclivre.com/*
// @match        https://www.momox-shop.fr/*
// @match        https://momox-shop.fr/*
// @grant        GM_info
// @run-at       document-start
// ==/UserScript==

(function () {
    'use strict';

    console.log('[AutoBuy] Script v2.1 loaded on', window.location.hostname);

    // Step-based autobuy: flag = JSON {step, ts}
    // Only activates on the EXPECTED page for each step.
    // Browsing normally never matches because step won't be set.
    const AUTOBUY_TTL_MS = 90 * 1000; // 90s hard timeout
    const FLAG_KEY = 'resell_autobuy';

    function setFlag(step) {
        sessionStorage.setItem(FLAG_KEY, JSON.stringify({ step: step, ts: Date.now() }));
    }

    function getFlag() {
        const raw = sessionStorage.getItem(FLAG_KEY);
        if (!raw) return null;
        try {
            const flag = JSON.parse(raw);
            if (Date.now() - flag.ts > AUTOBUY_TTL_MS) {
                console.log('[AutoBuy] Flag expired, clearing');
                sessionStorage.removeItem(FLAG_KEY);
                return null;
            }
            return flag;
        } catch (e) {
            // Old format ('1' or timestamp) — clear it
            sessionStorage.removeItem(FLAG_KEY);
            return null;
        }
    }

    function clearFlag() {
        sessionStorage.removeItem(FLAG_KEY);
    }

    // ── Trigger detection ─────────────────────────────────────
    const hash = window.location.hash;
    const url = new URL(window.location.href);

    if (hash.startsWith('#autobuy=')) {
        // Relay mode (Momox): homepage → set flag for product step → navigate
        const targetPath = decodeURIComponent(hash.substring('#autobuy='.length));
        console.log('[AutoBuy] Relay → product:', targetPath);
        setFlag('product');
        window.location.href = targetPath;
        return;
    }

    if (hash === '#autobuy' || url.searchParams.has('autobuy')) {
        // Direct mode (RecycLivre): set flag for product step
        console.log('[AutoBuy] Direct trigger → product');
        setFlag('product');
        url.searchParams.delete('autobuy');
        url.hash = '';
        try { (unsafeWindow || window).history.replaceState({}, '', url.toString()); } catch(e) {}
    }

    const flag = getFlag();
    if (!flag) {
        // No flag or expired — do nothing. Normal browsing is never affected.
        return;
    }

    console.log('[AutoBuy] Active step:', flag.step, 'on', window.location.pathname);

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

    // Wait for DOM
    function onReady(fn) {
        if (document.readyState === 'complete' || document.readyState === 'interactive') {
            setTimeout(fn, 100);
        } else {
            document.addEventListener('DOMContentLoaded', fn);
        }
    }

    onReady(function () {
        runAutoBuy(flag.step);
    });

    // ── Main logic ────────────────────────────────────────────

    function runAutoBuy(step) {
        const hostname = window.location.hostname;
        const path = window.location.pathname;

        // ── RecycLivre ────────────────────────────────────────
        if (hostname.includes('recyclivre.com')) {

            if (step === 'product' && path.startsWith('/products/') && !path.includes('carte-cadeau')) {
                (async () => {
                    showBanner('AutoBuy: ajout au panier...');
                    try {
                        await sleep(1500);
                        await waitClickAny([
                            'button[onclick="clickToTheRightButton()"]',
                            'button.btn-primary-darker.w-full',
                            '#sylius-product-adding-to-cart button.btn-primary-darker',
                        ]);
                        setFlag('cart'); // Next expected step
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
                            window.location.href = '/cart/';
                        }
                    } catch (e) {
                        console.warn(e.message);
                        clearFlag();
                        showBanner('AutoBuy: bouton non trouve, verifie la page');
                    }
                })();
                return;
            }

            if (step === 'cart' && (path === '/cart' || path === '/cart/')) {
                (async () => {
                    showBanner('AutoBuy: validation du panier...');
                    try {
                        await sleep(1500);
                        setFlag('checkout'); // Next expected step
                        await waitClickAny([
                            'a[href="/checkout"]',
                            'a[href="/checkout/"]',
                            'a[href*="checkout"].btn',
                        ]);
                    } catch (e) {
                        console.warn(e.message);
                        clearFlag();
                        showBanner('AutoBuy: bouton Valider non trouve');
                    }
                })();
                return;
            }

            if (step === 'checkout' && path.startsWith('/checkout')) {
                clearFlag();
                showBanner('AutoBuy: checkout atteint ! Complete le paiement.');
                return;
            }
        }

        // ── Momox Shop ────────────────────────────────────────
        if (hostname.includes('momox-shop.fr')) {

            if (step === 'product' && path.endsWith('.html') && !path.includes('Panier') && !path.includes('Donnees') && !path.includes('Paiement') && !path.includes('Confirmation')) {
                (async () => {
                    showBanner('AutoBuy: ajout au panier...');
                    try {
                        await sleep(1500);
                        try {
                            const cookieBtn = document.querySelector('[data-testid="uc-accept-all-button"], .uc-accept-all-button');
                            if (cookieBtn) { cookieBtn.click(); await sleep(1000); }
                        } catch(e) {}

                        await waitClickAny([
                            'button[data-cnstrc-btn="add_to_cart"][aria-label="buy"]',
                            'button[data-cnstrc-btn="add_to_cart"]',
                            'button[aria-label="buy"]',
                        ]);

                        setFlag('cart'); // Next expected step
                        showBanner('AutoBuy: article ajoute ! Passage en caisse...');
                        await sleep(2500);

                        try {
                            await waitClickAny([
                                'a[href*="/Panier"]',
                            ], 3000);
                        } catch (e) {
                            const btn = findVisibleByText('Passer');
                            if (btn) {
                                btn.click();
                            } else {
                                window.location.href = '/Panier/';
                            }
                        }
                    } catch (e) {
                        console.warn(e.message);
                        clearFlag();
                        showBanner('AutoBuy: bouton non trouve');
                    }
                })();
                return;
            }

            if (step === 'cart' && path.includes('Panier')) {
                (async () => {
                    showBanner('AutoBuy: passage en caisse...');
                    try {
                        await sleep(1500);
                        setFlag('shipping');
                        await waitClickAny([
                            'button.cart-page__checkout-button',
                            'button[href*="Donnees-Personnelles"]',
                            'a[href*="Donnees-Personnelles"]',
                        ], 8000);
                    } catch (e) {
                        const btn = findVisibleByText('Passer');
                        if (btn) btn.click();
                        else { clearFlag(); console.warn('[AutoBuy] Checkout button not found'); }
                    }
                })();
                return;
            }

            if (step === 'shipping' && path.includes('Donnees-Personnelles')) {
                (async () => {
                    showBanner('AutoBuy: confirmation livraison...');
                    try {
                        await sleep(2000);
                        setFlag('payment');
                        await waitClickAny([
                            'button[type="submit"]',
                            'input[type="submit"]',
                        ], 5000);
                    } catch (e) {
                        const btn = findVisibleByText('Continuer') || findVisibleByText('Weiter');
                        if (btn) btn.click();
                        else clearFlag();
                    }
                })();
                return;
            }

            if (step === 'payment' && path.includes('Paiement')) {
                clearFlag();
                showBanner('AutoBuy: page de paiement atteinte !');
                return;
            }

            if (path.includes('Confirmation')) {
                clearFlag();
                showBanner('AutoBuy: commande confirmee !');
                return;
            }
        }

        // If we get here, step doesn't match current page — stale flag, clear it
        console.log('[AutoBuy] Step "' + step + '" does not match page ' + path + ', clearing');
        clearFlag();
    }
})();
