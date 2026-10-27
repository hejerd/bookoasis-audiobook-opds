// Official dashboard bundle: all rendering stays inside this widget's Shadow DOM.
(() => {
  const list = shadowRoot.querySelector('.books');
  const status = shadowRoot.querySelector('.status');
  const refresh = shadowRoot.querySelector('.refresh');
  const node = (tag, cls, text) => {
    const el = document.createElement(tag);
    el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const duration = (value) => {
    const seconds = Math.max(0, Math.floor(value));
    const h = Math.floor(seconds / 3600);
    const m = Math.floor(seconds % 3600 / 60);
    const s = seconds % 60;
    return (h ? `${h}시간 ` : '') + (m ? `${m}분 ` : '') + `${s}초`;
  };
  const percentage = (value) => value > 0 && value < .1 ? '0.1% 미만' : `${Math.min(value < 100 ? 99.9 : 100, Math.round(value * 10) / 10)}%`;
  function render(rows) {
    list.replaceChildren();
    for (const item of rows) {
      if (!Number.isSafeInteger(item.bookId) || item.bookId < 1) continue;
      const card = node('article', 'book');
      const cover = node('div', 'cover');
      if (item.cover === `/api/media/audiobooks/${item.bookId}/cover`) {
        const img = node('img', 'cover');
        img.src = item.cover;
        img.alt = '';
        img.loading = 'lazy';
        img.addEventListener('error', () => img.remove(), { once: true });
        cover.append(img);
      }
      const info = node('div', 'info');
      const title = node('button', 'title', item.title);
      title.type = 'button';
      title.setAttribute('aria-label', `${item.title} 이어 듣기`);
      title.addEventListener('click', () => {
        if (typeof window.openAudioPlayer === 'function') window.openAudioPlayer(item.bookId);
        else status.textContent = '홈 화면을 새로고침한 뒤 다시 눌러 주세요.';
      });
      info.append(title, node('div', 'author', item.author));
      const line = node('div', 'position');
      line.append(node('span', 'episode', item.trackIndex ? `${item.trackIndex} / ${item.trackCount}화` : `전체 ${item.trackCount}화`));
      if (Number.isFinite(item.percent)) {
        const pct = Math.min(100, Math.max(0, item.percent));
        const label = item.completed ? '완료' : `${item.basis === 'tracks' ? '회차 기준 약 ' : '전체 '}${percentage(pct)}`;
        line.append(node('span', 'percent', label));
        info.append(line);
        const bar = node('progress', 'progress');
        bar.max = 100;
        bar.value = pct;
        bar.setAttribute('aria-label', label);
        info.append(bar);
      } else {
        info.append(line);
      }
      if (Number.isFinite(item.total) && Number.isFinite(item.elapsed)) {
        info.append(node('div', 'duration', `현재 위치 ${duration(item.elapsed)}`),
          node('div', 'duration', `전체 ${duration(item.total)}`),
          node('div', 'remaining', `전체 ${duration(Math.ceil(item.remaining))} 남음`));
      } else {
        info.append(node('div', 'duration', '전체 시간 확인 전'));
      }
      card.append(cover, info);
      list.append(card);
    }
    status.textContent = list.children.length ? '' : '최근 들은 오디오북이 없습니다. 앱이나 웹에서 재생하면 여기에 표시됩니다.';
  }
  let busy = false;
  async function update() {
    if (busy || !shadowRoot.host.isConnected || document.hidden) return;
    busy = true;
    refresh.disabled = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(`/api/media/dashboard/widgets/${encodeURIComponent(pluginId)}/data?type=audiobook&limit=6`,
        { credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
      const data = await response.json();
      if (!shadowRoot.host.isConnected) return;
      if (!response.ok || !data.success || !Array.isArray(data.items)) throw new Error('unavailable');
      render(data.items);
    } catch (_) {
      // Do not keep potentially revoked/private data visible after a failed refresh.
      list.replaceChildren();
      status.textContent = '청취 진행률을 불러오지 못했습니다. 연결·로그인 상태를 확인하고 새로고침해 주세요.';
    } finally {
      clearTimeout(timeout);
      busy = false;
      refresh.disabled = false;
    }
  }
  render(items);
  refresh.addEventListener('click', update);
  const timer = setInterval(() => {
    if (!shadowRoot.host.isConnected) clearInterval(timer);
    else update();
  }, 30000);
})();
