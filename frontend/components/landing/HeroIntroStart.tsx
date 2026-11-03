'use client';

import { useEffect, useRef, useSyncExternalStore } from 'react';

/*
 * 히어로 인트로 애니메이션 시작 신호(.landing-hero에 hero-go / hero-skip 클래스를 붙인다).
 * 글꼴(Pretendard)이 준비된 뒤에 시작해서, 글꼴 교체로 화면 전체를 다시 계산하는 순간이
 * 애니메이션 한가운데 겹치지 않게 한다. 1.5초 안에 글꼴이 오지 않으면(느린 회선) 인트로 없이
 * 완성된 화면을 바로 보여준다. 대체 글꼴(Fallback) 면은 기기에 따라 실패할 수 있어 본 글꼴만 기다린다.
 * 글꼴은 글자 묶음별로 나뉘어 있어(app/fonts/pretendard.css) 히어로에 실제로 쓰인 글자가 든 묶음만
 * 기다린다 — 보통 영문·히어로 두 파일(약 60KB).
 *
 * 두 경로에서 같은 코드(START_BODY)를 실행한다.
 *  - 첫 방문·새로고침: 서버 HTML의 <script>가 하이드레이션 전에 바로 실행된다.
 *  - 다른 화면에서 링크로 들어올 때: React가 넣은 <script>는 실행되지 않으므로 useEffect에서 실행한다.
 * 이미 클래스가 붙어 있으면 아무것도 하지 않아서 두 번 실행돼도 안전하다.
 * <script>는 서버 HTML과 하이드레이션 때만 그리고, 링크 이동으로 새로 그릴 때는 빼서
 * React의 "실행되지 않는 script" 경고가 나지 않게 한다.
 */
const START_BODY = `if(!h||/hero-(go|skip)/.test(h.className))return;
function go(c){if(!/hero-(go|skip)/.test(h.className))h.classList.add(c);}
var f=document.fonts;
var fam=getComputedStyle(document.documentElement).getPropertyValue('--font-pretendard');
if(!f||!f.load||!fam){go('hero-go');return;}
setTimeout(function(){go('hero-skip');},1500);
var ok=function(){go('hero-go');};
f.load('900 100px '+fam.split(',')[0],h.textContent||'A').then(ok,function(){f.ready.then(ok,ok);});`;

const START_SCRIPT = `(function(h){${START_BODY}})(document.currentScript&&document.currentScript.parentElement);`;

const noopSubscribe = () => () => {};

export default function HeroIntroStart() {
  const ref = useRef<HTMLSpanElement>(null);
  // 서버 렌더링·하이드레이션 중에는 true, 브라우저에서 새로 그릴 때는 false
  const fromServer = useSyncExternalStore(
    noopSubscribe,
    () => false,
    () => true
  );

  useEffect(() => {
    const start = new Function('h', START_BODY) as (
      h: HTMLElement | null
    ) => void;
    start(ref.current?.parentElement ?? null);
  }, []);

  return (
    <>
      <span ref={ref} hidden />
      {fromServer && (
        <script dangerouslySetInnerHTML={{ __html: START_SCRIPT }} />
      )}
    </>
  );
}
