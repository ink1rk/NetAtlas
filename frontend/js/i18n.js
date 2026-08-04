/**
 * NetAtlas i18n — RU (default) / EN
 */
const I18n = (() => {
  const STORAGE_KEY = 'netatlas_lang';
  const SUPPORTED = ['ru', 'en'];

  const DICT = {
    ru: {
      'nav.overview': 'Обзор',
      'nav.inventory': 'Инвентарь',
      'nav.operations': 'Операции',
      'nav.dashboard': 'Панель',
      'nav.topology': 'Топология',
      'nav.monitoring': 'Мониторинг',
      'nav.observability': 'Наблюдаемость',
      'nav.devices': 'Устройства',
      'nav.search': 'Поиск',
      'nav.ipam': 'IPAM',
      'nav.discovery': 'Обнаружение',
      'nav.snapshots': 'Снимки',
      'shell.operator': 'оператор',
      'shell.logout': 'Выйти',
      'shell.lang': 'Язык',

      'login.title': 'NetAtlas — Вход',
      'login.tagline': 'Цифровой атлас корпоративной инфраструктуры — топология, инвентарь и наблюдаемость в одном центре управления знаниями.',
      'login.heading': 'Доступ оператора',
      'login.subtitle': 'Войдите, чтобы открыть консоль сетевых операций.',
      'login.username': 'Имя пользователя',
      'login.password': 'Пароль',
      'login.submit': 'Войти',
      'login.signing_in': 'Вход…',
      'login.auth_failed': 'Ошибка аутентификации',

      'title.dashboard': 'Панель',
      'title.topology': 'Карта топологии',
      'title.monitoring': 'Системный мониторинг',
      'title.observability': 'Наблюдаемость',
      'title.devices': 'Инвентарь устройств',
      'title.device_detail': 'Карточка устройства',
      'title.search': 'Единый поиск',
      'title.ipam': 'Управление IP-адресами',
      'title.discovery': 'Обнаружение сети',
      'title.snapshots': 'Снимки и сравнение',

      'common.loading': 'Загрузка…',
      'common.filter': 'Фильтр',
      'common.search': 'Найти',
      'common.prev': 'Назад',
      'common.next': 'Далее',
      'common.yes': 'Да',
      'common.no': 'Нет',
      'common.none': 'Нет',
      'common.remove': 'Удалить',
      'common.refresh': 'Обновить',
      'common.status': 'Статус',
      'common.vendor': 'Вендор',
      'common.model': 'Модель',
      'common.hostname': 'Имя узла',
      'common.time': 'Время',
      'common.message': 'Сообщение',
      'common.source': 'Источник',
      'common.severity': 'Критичность',
      'common.page_of': 'Стр. {page} из {total}',

      'status.up': 'в сети',
      'status.down': 'недоступен',
      'status.running': 'выполняется',
      'status.completed': 'завершён',
      'status.failed': 'ошибка',
      'status.pending': 'ожидание',
      'status.cancelled': 'отменён',
      'status.problem': 'проблема',
      'status.ok': 'норма',
      'status.unknown': 'неизвестно',
      'status.used': 'занят',
      'status.free': 'свободен',
      'status.reserved': 'зарезервирован',

      'unit.gbps': 'Гбит/с',
      'unit.mbps': 'Мбит/с',
      'unit.bps': 'бит/с',
      'unit.days': 'дн.',

      'dash.devices': 'Устройства',
      'dash.links': 'Связи',
      'dash.prefixes': 'Префиксы',
      'dash.alerts': 'Алерты',
      'dash.live_map': 'Живая карта сети',
      'dash.fullscreen': 'На весь экран',
      'dash.loading_health': 'Загрузка состояния…',
      'dash.trigger_problems': '{n} проблем триггеров',
      'dash.syslog_events': '{n} событий syslog',
      'dash.nodes_mapped': '{n} узлов на карте',
      'dash.observability': 'Наблюдаемость',

      'topo.fit': 'Вписать',
      'topo.relayout': 'Перестроить',
      'topo.loading': 'Загрузка топологии…',
      'topo.failed': 'Не удалось загрузить топологию: {msg}',

      'devices.all': 'Все устройства',
      'devices.search_ph': 'Поиск по имени…',
      'devices.vendor_ph': 'Вендор',
      'devices.empty': 'Нет устройств по заданным фильтрам.',
      'devices.count': '{n} устройств',
      'devices.mgmt_ip': 'Management IP',
      'devices.os': 'Версия ОС',
      'devices.last_seen': 'Последний контакт',
      'devices.platform': 'Платформа',

      'device.loading': 'Загрузка устройства…',
      'device.back': '← К инвентарю',
      'device.serial': 'Серийный номер',
      'device.firmware': 'Прошивка',
      'device.os': 'Версия ОС',
      'device.last_seen': 'Последний контакт',
      'device.tab_ifaces': 'Интерфейсы',
      'device.tab_neighbors': 'Соседи',
      'device.tab_metrics': 'Метрики',
      'device.no_ifaces': 'Интерфейсы не найдены.',
      'device.no_neighbors': 'Соседи не обнаружены.',
      'device.no_metrics': 'История метрик недоступна.',
      'device.iface_name': 'Имя',
      'device.speed': 'Скорость',
      'device.local_iface': 'Локальный интерфейс',
      'device.remote_device': 'Удалённое устройство',
      'device.remote_iface': 'Удалённый интерфейс',
      'device.protocol': 'Протокол',
      'device.cpu': 'CPU %',
      'device.memory': 'Память %',

      'search.placeholder': 'Поиск устройств, интерфейсов, IP-адресов…',
      'search.hint': 'Введите запрос для поиска по инвентарю.',
      'search.searching': 'Поиск…',
      'search.no_results': 'Ничего не найдено по запросу «{q}».',
      'search.results_for': '{n} по запросу «{q}»',
      'search.devices': 'Устройства ({n})',
      'search.interfaces': 'Интерфейсы ({n})',
      'search.addresses': 'Адреса ({n})',
      'search.conflict': 'конфликт',
      'search.result_one': '{n} результат',
      'search.result_few': '{n} результата',
      'search.result_many': '{n} результатов',

      'ipam.prefixes': 'Префиксы',
      'ipam.prefix_cidr': 'Префикс (CIDR)',
      'ipam.description': 'Описание',
      'ipam.desc_ph': 'Корпоративная LAN',
      'ipam.register': 'Зарегистрировать',
      'ipam.utilization': 'Утилизация',
      'ipam.addresses': 'Адреса',
      'ipam.select_prefix': 'Выберите префикс, чтобы увидеть адреса.',
      'ipam.no_prefixes': 'Префиксы не зарегистрированы.',
      'ipam.usage': 'занято {used} · свободно {free} · конфликты {conflicts}',
      'ipam.addresses_for': 'Адреса — {prefix}',
      'ipam.no_addresses': 'В этом префиксе нет адресов.',
      'ipam.address': 'Адрес',
      'ipam.mac': 'MAC',
      'ipam.conflict': 'Конфликт',

      'disc.seeds': 'Сид-адреса',
      'disc.target': 'Цель (IP или CIDR)',
      'disc.label': 'Метка',
      'disc.label_ph': 'Ядро сети',
      'disc.add_seed': 'Добавить сид',
      'disc.jobs': 'Задания обнаружения',
      'disc.start': 'Запустить',
      'disc.no_seeds': 'Сиды не настроены.',
      'disc.confirm_remove': 'Удалить этот сид?',
      'disc.no_jobs': 'Заданий обнаружения пока нет.',
      'disc.started': 'Начало',
      'disc.finished': 'Окончание',
      'disc.stats': 'Статистика',

      'mon.api_health': 'Здоровье API',
      'mon.readiness': 'Готовность',
      'mon.version': 'Версия',
      'mon.devices_up': 'Устройства в сети',
      'mon.device_health': 'Состояние устройств',
      'mon.job_activity': 'Активность заданий обнаружения',
      'mon.device_metrics': 'Метрики устройств',
      'mon.error': 'Ошибка',
      'mon.ready': 'Готов',
      'mon.not_ready': 'Не готов',
      'mon.up': 'В сети',
      'mon.down': 'Недоступны',
      'mon.unknown': 'Неизвестно',
      'mon.jobs': 'Задания',
      'mon.no_metrics': 'Метрики устройств недоступны.',
      'mon.device': 'Устройство',
      'mon.uptime': 'Аптайм',
      'mon.last_polled': 'Последний опрос',

      'obs.subtitle': 'Локальный syslog · триггеры · SMTP-алерты · частичный SIEM',
      'obs.triggers': 'Триггеры',
      'obs.name': 'Имя',
      'obs.kind': 'Тип',
      'obs.last_value': 'Последнее значение',
      'obs.changed': 'Изменён',
      'obs.no_triggers': 'Триггеров нет',
      'obs.recent_alerts': 'Недавние алерты',
      'obs.type': 'Тип',
      'obs.ack': 'Подтв.',
      'obs.ack_btn': 'Подтвердить',
      'obs.no_alerts': 'Алертов пока нет',
      'obs.events': 'События Syslog / SIEM',
      'obs.search_msg': 'Поиск по сообщению',
      'obs.all_categories': 'Все категории',
      'obs.sev': 'Сев.',
      'obs.category': 'Категория',
      'obs.no_events': 'Событий нет',
      'obs.siem': 'Корреляции SIEM',
      'obs.rule': 'Правило',
      'obs.hit_title': 'Заголовок',
      'obs.no_siem': 'Корреляций нет',
      'obs.on': 'вкл',
      'obs.off': 'выкл',
      'obs.events_count': '{n} событий',
      'obs.problems_count': '{n} проблем',

      'snap.archive': 'Архив снимков',
      'snap.compare': 'Сравнение снимков',
      'snap.left': 'Левый снимок',
      'snap.right': 'Правый снимок',
      'snap.compare_btn': 'Сравнить',
      'snap.empty': 'Снимков пока нет.',
      'snap.label': 'Метка',
      'snap.created': 'Создан',
      'snap.checksum': 'Контрольная сумма',
      'snap.summary': 'Сводка',
      'snap.select_two': 'Выберите два снимка',
      'snap.computing': 'Вычисление различий…',
      'snap.added': 'Добавлено ({n})',
      'snap.removed': 'Удалено ({n})',
      'snap.changed': 'Изменено ({n})',

      'api.no_refresh': 'Нет токена обновления',
      'api.refresh_failed': 'Не удалось обновить сессию',
      'api.session_expired': 'Сессия истекла',
    },
    en: {
      'nav.overview': 'Overview',
      'nav.inventory': 'Inventory',
      'nav.operations': 'Operations',
      'nav.dashboard': 'Dashboard',
      'nav.topology': 'Topology',
      'nav.monitoring': 'Monitoring',
      'nav.observability': 'Observability',
      'nav.devices': 'Devices',
      'nav.search': 'Search',
      'nav.ipam': 'IPAM',
      'nav.discovery': 'Discovery',
      'nav.snapshots': 'Snapshots',
      'shell.operator': 'operator',
      'shell.logout': 'Sign out',
      'shell.lang': 'Language',

      'login.title': 'NetAtlas — Sign In',
      'login.tagline': 'The digital atlas of your enterprise infrastructure — topology, inventory, and observability in one knowledge command center.',
      'login.heading': 'Operator access',
      'login.subtitle': 'Authenticate to enter the network operations console.',
      'login.username': 'Username',
      'login.password': 'Password',
      'login.submit': 'Sign in',
      'login.signing_in': 'Signing in…',
      'login.auth_failed': 'Authentication failed',

      'title.dashboard': 'Dashboard',
      'title.topology': 'Topology Map',
      'title.monitoring': 'System Monitoring',
      'title.observability': 'Observability',
      'title.devices': 'Device Inventory',
      'title.device_detail': 'Device Detail',
      'title.search': 'Unified Search',
      'title.ipam': 'IP Address Management',
      'title.discovery': 'Network Discovery',
      'title.snapshots': 'Snapshots & Diff',

      'common.loading': 'Loading…',
      'common.filter': 'Filter',
      'common.search': 'Search',
      'common.prev': 'Previous',
      'common.next': 'Next',
      'common.yes': 'Yes',
      'common.no': 'No',
      'common.none': 'None',
      'common.remove': 'Remove',
      'common.refresh': 'Refresh',
      'common.status': 'Status',
      'common.vendor': 'Vendor',
      'common.model': 'Model',
      'common.hostname': 'Hostname',
      'common.time': 'Time',
      'common.message': 'Message',
      'common.source': 'Source',
      'common.severity': 'Severity',
      'common.page_of': 'Page {page} of {total}',

      'status.up': 'up',
      'status.down': 'down',
      'status.running': 'running',
      'status.completed': 'completed',
      'status.failed': 'failed',
      'status.pending': 'pending',
      'status.cancelled': 'cancelled',
      'status.problem': 'problem',
      'status.ok': 'ok',
      'status.unknown': 'unknown',
      'status.used': 'used',
      'status.free': 'free',
      'status.reserved': 'reserved',

      'unit.gbps': 'Gbps',
      'unit.mbps': 'Mbps',
      'unit.bps': 'bps',
      'unit.days': 'd',

      'dash.devices': 'Devices',
      'dash.links': 'Links',
      'dash.prefixes': 'Prefixes',
      'dash.alerts': 'Alerts',
      'dash.live_map': 'Live Network Map',
      'dash.fullscreen': 'Full screen',
      'dash.loading_health': 'Loading health status…',
      'dash.trigger_problems': '{n} trigger problems',
      'dash.syslog_events': '{n} syslog events stored',
      'dash.nodes_mapped': '{n} nodes mapped',
      'dash.observability': 'Observability',

      'topo.fit': 'Fit view',
      'topo.relayout': 'Re-layout',
      'topo.loading': 'Loading topology…',
      'topo.failed': 'Failed to load topology: {msg}',

      'devices.all': 'All Devices',
      'devices.search_ph': 'Search hostname…',
      'devices.vendor_ph': 'Vendor',
      'devices.empty': 'No devices match your filters.',
      'devices.count': '{n} devices',
      'devices.mgmt_ip': 'Management IP',
      'devices.os': 'OS Version',
      'devices.last_seen': 'Last Seen',
      'devices.platform': 'Platform',

      'device.loading': 'Loading device…',
      'device.back': '← Back to inventory',
      'device.serial': 'Serial',
      'device.firmware': 'Firmware',
      'device.os': 'OS Version',
      'device.last_seen': 'Last Seen',
      'device.tab_ifaces': 'Interfaces',
      'device.tab_neighbors': 'Neighbors',
      'device.tab_metrics': 'Metrics',
      'device.no_ifaces': 'No interfaces.',
      'device.no_neighbors': 'No neighbors discovered.',
      'device.no_metrics': 'No metrics history available.',
      'device.iface_name': 'Name',
      'device.speed': 'Speed',
      'device.local_iface': 'Local Interface',
      'device.remote_device': 'Remote Device',
      'device.remote_iface': 'Remote Interface',
      'device.protocol': 'Protocol',
      'device.cpu': 'CPU %',
      'device.memory': 'Memory %',

      'search.placeholder': 'Search devices, interfaces, IP addresses…',
      'search.hint': 'Enter a query to search across inventory.',
      'search.searching': 'Searching…',
      'search.no_results': 'No results for "{q}".',
      'search.results_for': '{n} for "{q}"',
      'search.devices': 'Devices ({n})',
      'search.interfaces': 'Interfaces ({n})',
      'search.addresses': 'Addresses ({n})',
      'search.conflict': 'conflict',
      'search.result_one': '{n} result',
      'search.result_few': '{n} results',
      'search.result_many': '{n} results',

      'ipam.prefixes': 'Prefixes',
      'ipam.prefix_cidr': 'Prefix (CIDR)',
      'ipam.description': 'Description',
      'ipam.desc_ph': 'Corporate LAN',
      'ipam.register': 'Register',
      'ipam.utilization': 'Utilization',
      'ipam.addresses': 'Addresses',
      'ipam.select_prefix': 'Select a prefix to view addresses.',
      'ipam.no_prefixes': 'No prefixes registered.',
      'ipam.usage': 'used {used} · free {free} · conflicts {conflicts}',
      'ipam.addresses_for': 'Addresses — {prefix}',
      'ipam.no_addresses': 'No addresses in this prefix.',
      'ipam.address': 'Address',
      'ipam.mac': 'MAC',
      'ipam.conflict': 'Conflict',

      'disc.seeds': 'Discovery Seeds',
      'disc.target': 'Target (IP or CIDR)',
      'disc.label': 'Label',
      'disc.label_ph': 'Core network',
      'disc.add_seed': 'Add Seed',
      'disc.jobs': 'Discovery Jobs',
      'disc.start': 'Start Job',
      'disc.no_seeds': 'No seeds configured.',
      'disc.confirm_remove': 'Remove this seed?',
      'disc.no_jobs': 'No discovery jobs yet.',
      'disc.started': 'Started',
      'disc.finished': 'Finished',
      'disc.stats': 'Stats',

      'mon.api_health': 'API Health',
      'mon.readiness': 'Readiness',
      'mon.version': 'Version',
      'mon.devices_up': 'Devices Up',
      'mon.device_health': 'Device Health Overview',
      'mon.job_activity': 'Discovery Job Activity',
      'mon.device_metrics': 'Device Metrics',
      'mon.error': 'Error',
      'mon.ready': 'Ready',
      'mon.not_ready': 'Not Ready',
      'mon.up': 'Up',
      'mon.down': 'Down',
      'mon.unknown': 'Unknown',
      'mon.jobs': 'Jobs',
      'mon.no_metrics': 'No device metrics available.',
      'mon.device': 'Device',
      'mon.uptime': 'Uptime',
      'mon.last_polled': 'Last Polled',

      'obs.subtitle': 'Onboard syslog · triggers · SMTP alerts · partial SIEM',
      'obs.triggers': 'Triggers',
      'obs.name': 'Name',
      'obs.kind': 'Kind',
      'obs.last_value': 'Last value',
      'obs.changed': 'Changed',
      'obs.no_triggers': 'No triggers',
      'obs.recent_alerts': 'Recent alerts',
      'obs.type': 'Type',
      'obs.ack': 'Ack',
      'obs.ack_btn': 'Ack',
      'obs.no_alerts': 'No alerts yet',
      'obs.events': 'Syslog / SIEM events',
      'obs.search_msg': 'Search message',
      'obs.all_categories': 'All categories',
      'obs.sev': 'Sev',
      'obs.category': 'Category',
      'obs.no_events': 'No events',
      'obs.siem': 'SIEM correlation hits',
      'obs.rule': 'Rule',
      'obs.hit_title': 'Title',
      'obs.no_siem': 'No correlation hits',
      'obs.on': 'on',
      'obs.off': 'off',
      'obs.events_count': '{n} events',
      'obs.problems_count': '{n} problems',

      'snap.archive': 'Snapshot Archive',
      'snap.compare': 'Compare Snapshots',
      'snap.left': 'Left snapshot',
      'snap.right': 'Right snapshot',
      'snap.compare_btn': 'Compare',
      'snap.empty': 'No snapshots captured yet.',
      'snap.label': 'Label',
      'snap.created': 'Created',
      'snap.checksum': 'Checksum',
      'snap.summary': 'Summary',
      'snap.select_two': 'Select two snapshots',
      'snap.computing': 'Computing diff…',
      'snap.added': 'Added ({n})',
      'snap.removed': 'Removed ({n})',
      'snap.changed': 'Changed ({n})',

      'api.no_refresh': 'No refresh token',
      'api.refresh_failed': 'Refresh failed',
      'api.session_expired': 'Session expired',
    },
  };

  function normalize(code) {
    const base = String(code || '').toLowerCase().slice(0, 2);
    return SUPPORTED.includes(base) ? base : 'ru';
  }

  function detect() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return normalize(saved);
    const nav = (navigator.language || 'ru').toLowerCase();
    return nav.startsWith('en') ? 'en' : 'ru';
  }

  let current = detect();

  function lang() {
    return current;
  }

  function locale() {
    return current === 'en' ? 'en-US' : 'ru-RU';
  }

  function setLang(code) {
    current = normalize(code);
    localStorage.setItem(STORAGE_KEY, current);
    document.documentElement.lang = current;
    window.location.reload();
  }

  function t(key, vars) {
    const table = DICT[current] || DICT.ru;
    let text = table[key] ?? DICT.ru[key] ?? key;
    if (vars) {
      Object.entries(vars).forEach(([k, v]) => {
        text = text.replaceAll(`{${k}}`, String(v));
      });
    }
    return text;
  }

  function statusLabel(status) {
    const s = (status || 'unknown').toLowerCase();
    return t(`status.${s}`) === `status.${s}` ? (status || t('status.unknown')) : t(`status.${s}`);
  }

  function applyDom(root = document) {
    document.documentElement.lang = current;
    root.querySelectorAll('[data-i18n]').forEach((el) => {
      el.textContent = t(el.getAttribute('data-i18n'));
    });
    root.querySelectorAll('[data-i18n-html]').forEach((el) => {
      el.innerHTML = t(el.getAttribute('data-i18n-html'));
    });
    root.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
      el.setAttribute('placeholder', t(el.getAttribute('data-i18n-placeholder')));
    });
    root.querySelectorAll('[data-i18n-title]').forEach((el) => {
      document.title = t(el.getAttribute('data-i18n-title'));
    });
    root.querySelectorAll('[data-lang]').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-lang') === current);
    });
  }

  function langSwitcherHtml(extraClass = '') {
    return `
      <div class="lang-switch ${extraClass}" role="group" aria-label="${t('shell.lang')}">
        <button type="button" class="lang-btn${current === 'ru' ? ' active' : ''}" data-lang="ru">RU</button>
        <button type="button" class="lang-btn${current === 'en' ? ' active' : ''}" data-lang="en">EN</button>
      </div>
    `;
  }

  function bindLangSwitcher(root = document) {
    root.querySelectorAll('[data-lang]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const next = btn.getAttribute('data-lang');
        if (next && next !== current) setLang(next);
      });
    });
  }

  document.documentElement.lang = current;

  return {
    t, lang, locale, setLang, applyDom, bindLangSwitcher, langSwitcherHtml, statusLabel, SUPPORTED,
  };
})();
