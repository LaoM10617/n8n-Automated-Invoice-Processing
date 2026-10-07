/* Notification recovery is independent of approval and workbook creation. */
(() => {
  window.showOutcomeNotification = async (kind, id, container) => {
    const endpoint = '/api/ap/result-notifications/' + kind + '/' + encodeURIComponent(id);
    container.replaceChildren();
    const status = document.createElement('p'); status.className = 'meta'; status.setAttribute('role', 'status');
    status.textContent = 'Loading result notification…'; container.append(status);
    try {
      const response = await fetch(endpoint, {cache: 'no-store'});
      if (!response.ok) throw new Error('Cannot read notification. Refresh to retry.');
      const notice = await response.json();
      status.textContent = `Result notification: ${notice.status} · Attempts ${notice.attempts}/${notice.max_attempts} · ${notice.last_error || notice.delivery_error || 'No notification error'}`;
      for (const [action, label] of [['refresh', 'Refresh notification'], ['retry', 'Retry notification'], ['check', 'Check Mailpit']]) {
        const button = document.createElement('button'); button.textContent = label;
        const uncertain = ['sending', 'unknown'].includes(notice.status);
        button.disabled = action === 'retry' && (uncertain || notice.status === 'sent' || notice.attempts >= notice.max_attempts) || action === 'check' && !uncertain;
        button.addEventListener('click', async () => {
          container.querySelectorAll('button').forEach(b => { b.disabled = true; });
          try {
            if (action !== 'refresh') {
              const result = await fetch(endpoint + '/' + action, {method: 'POST', headers: {'X-AP-Review': '1'}});
              const body = await result.json();
              if (!result.ok) throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
            }
            await window.showOutcomeNotification(kind, id, container);
          } catch (error) {
            await window.showOutcomeNotification(kind, id, container);
            container.querySelector('p').textContent += '\n' + error.message;
          }
        });
        container.append(button);
      }
      if (['unknown', 'sending'].includes(notice.status)) {
        const explanation = document.createElement('p'); explanation.className = 'meta';
        explanation.textContent = 'Wait 60 seconds, then check Mailpit by the saved Message-ID. Missing mail remains uncertain; it is never resent automatically.';
        container.append(explanation);
      }
    } catch (error) { status.textContent = error.message; }
  };
})();
