/*
 * Driver Manager Pro — Qt WebChannel ↔ pywebview API 호환 브릿지
 *
 * 목적: PyQt6 QtWebEngine + QtWebChannel 백엔드에서 기존 pywebview용
 * 프론트엔드(app.js)가 코드 수정 없이 동작하도록 호환 레이어를 제공한다.
 *
 * 동작 원리:
 *  1) qwebchannel.js가 노출하는 `qt.webChannelTransport`를 통해 채널을 연결한다.
 *  2) Python 측 API 객체(`api`)의 모든 슬롯을 Proxy로 감싸 각 메서드 호출을
 *     Promise로 반환되도록 변환한다.
 *  3) 결과 값이 JSON 문자열이면 자동 파싱하여 app.js가 기대하는 객체 형태로 돌려준다.
 *  4) 호환 완료 시 `window.pywebview = { api: <proxy> }` 형태로 노출하고
 *     `pywebviewready` 이벤트를 발생시켜 app.js의 초기화 흐름을 그대로 트리거한다.
 *
 * 의존성: qwebchannel.js (반드시 본 스크립트보다 먼저 로드되어야 한다)
 */
(function () {
  'use strict';

  // qt.webChannelTransport는 페이지가 QWebEnginePage에 의해 로드된 후 비동기로 주입된다.
  // 약간의 지연이 발생할 수 있으므로 짧은 폴링으로 대기한다.
  function waitForTransport(callback, retries) {
    if (typeof qt !== 'undefined' && qt.webChannelTransport) {
      callback();
      return;
    }
    if (retries <= 0) {
      console.error('[qtbridge] qt.webChannelTransport가 노출되지 않았습니다. QWebChannel 초기화 실패.');
      return;
    }
    setTimeout(function () { waitForTransport(callback, retries - 1); }, 50);
  }

  waitForTransport(function () {
    // QWebChannel은 qwebchannel.js의 전역 심볼이다.
    /* global QWebChannel */
    new QWebChannel(qt.webChannelTransport, function (channel) {
      var rawApi = channel.objects.api;
      if (!rawApi) {
        console.error('[qtbridge] api 객체가 채널에 등록되어 있지 않습니다.');
        return;
      }

      // 모든 메서드 호출을 Promise로 감싸는 Proxy. pywebview의 호출 규약과 동일.
      var apiProxy = new Proxy({}, {
        get: function (_target, methodName) {
          // Proxy는 Symbol 등 비호출 속성도 조회되므로 함수 외에는 그대로 반환한다.
          var target = rawApi[methodName];
          if (typeof target !== 'function') {
            return target;
          }
          return function () {
            var args = Array.prototype.slice.call(arguments);
            return new Promise(function (resolve) {
              // QWebChannel의 비동기 슬롯 호출은 마지막 콜백 인자로 결과를 받는다.
              args.push(function (result) {
                // Python 측에서 JSON 문자열로 직렬화한 경우 자동 파싱한다.
                // 일반 문자열/숫자/불리언/undefined는 그대로 전달한다.
                if (typeof result === 'string' && result.length > 0
                    && (result.charAt(0) === '{' || result.charAt(0) === '[')) {
                  try {
                    resolve(JSON.parse(result));
                    return;
                  } catch (e) {
                    // JSON 파싱 실패 시 원본 문자열 반환
                  }
                }
                resolve(result);
              });
              target.apply(rawApi, args);
            });
          };
        }
      });

      // pywebview 호환 인터페이스 노출
      window.pywebview = { api: apiProxy };

      // pywebview의 표준 준비 이벤트를 발생시켜 app.js init()을 트리거
      document.dispatchEvent(new Event('pywebviewready'));
      console.info('[qtbridge] window.pywebview.api 준비 완료');
    });
  }, 100);
})();
