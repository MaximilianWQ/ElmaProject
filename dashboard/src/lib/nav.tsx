import {
  LayoutDashboard, LineChart, Users, CreditCard, Megaphone, Share2, Gift,
  Ticket, Link2, Zap, ScrollText, Settings, Wrench,
  type LucideIcon,
} from "lucide-react";

export interface NavItem { to: string; label: string; icon: LucideIcon; }
export interface NavSection { label: string; items: NavItem[]; }

// One source of truth for both the desktop sidebar and the mobile sheet —
// they used to be two hand-kept copies, which is how a route ends up reachable
// on one and missing on the other.
export const sections: NavSection[] = [
  {
    label: "Главное",
    items: [
      { to: "", label: "Главная", icon: LayoutDashboard },
      { to: "analytics", label: "Аналитика", icon: LineChart },
      { to: "users", label: "Пользователи", icon: Users },
      { to: "payments", label: "Платежи", icon: CreditCard },
    ],
  },
  {
    label: "Маркетинг",
    items: [
      { to: "broadcasts", label: "Рассылки", icon: Megaphone },
      { to: "automations", label: "Автосообщения", icon: Zap },
      { to: "referrals", label: "Рефералы", icon: Share2 },
      { to: "gifts", label: "Гифты", icon: Gift },
      { to: "promo", label: "Промокоды", icon: Ticket },
      { to: "links", label: "Ссылки", icon: Link2 },
    ],
  },
  {
    label: "Система",
    items: [
      { to: "service", label: "Сервис", icon: Wrench },
      { to: "audit", label: "Аудит", icon: ScrollText },
      { to: "settings", label: "Настройки", icon: Settings },
    ],
  },
];

/** Flat list of every navigable item, in sidebar order. */
export const allItems: NavItem[] = sections.flatMap((s) => s.items);

/** Bottom bar on phones: four destinations plus the "Ещё" sheet. */
export const mobilePrimary: NavItem[] = [
  sections[0].items[0], // Главная
  sections[0].items[2], // Пользователи
  sections[0].items[3], // Платежи
  sections[1].items[0], // Рассылки
];

/** Everything that doesn't fit the bottom bar lives in the sheet. */
export const mobileMore: NavItem[] = allItems.filter(
  (it) => !mobilePrimary.includes(it),
);
