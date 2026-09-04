#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登录页与房间页统一战区视觉的静态回归检查。"""

from __future__ import print_function

import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(relative):
    with open(os.path.join(ROOT, relative), "r", encoding="utf-8") as handle:
        return handle.read()


def main():
    app = read("public/app.js")
    html = read("public/index.html")
    render = read("public/render3d.js")
    styles = read("public/styles.css")
    keyart = os.path.join(ROOT, "public", "assets", "front-war-keyart-v2.webp")

    assert 'class="front-stage"' in html
    assert 'class="front-keyart"' in html
    assert 'class="command-deck"' in html
    assert 'class="access-grid"' in html
    assert 'rel="preload" href="/assets/front-war-keyart-v2.webp"' in html
    assert 'url("/assets/front-war-keyart-v2.webp")' in styles
    assert os.path.getsize(keyart) > 100000

    for element_id in (
            "playerName", "roomName", "roomCodeInput", "createRoomBtn",
            "joinCodeBtn", "roomList", "serverStatus"):
        assert html.count('id="%s"' % element_id) == 1, element_id

    assert "document.body.setAttribute('data-front-screen', name)" in app
    assert "window.scrollTo(0, 0)" in app
    assert 'body[data-front-screen="game"] .front-stage' in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles

    # 重做后不再在首页持续渲染第二套 3D 场景，避免挤占对局帧预算。
    for obsolete in ("frontShowcase", "createFrontShowcase"):
        assert obsolete not in app
        assert obsolete not in render
        assert obsolete not in html

    print("front redesign ok: shared key art, command deck and briefing room")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
