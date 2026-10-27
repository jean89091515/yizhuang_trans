<template>
  <div class="sel" :class="[variant, { open, disabled }]" ref="root" @click.stop="toggle">
    <span class="val">{{ current?.label ?? placeholder }}</span>
    <svg v-if="variant === 'scheme'" class="chev tri" viewBox="0 0 12 8"><path d="M0 0h12L6 8z" /></svg>
    <svg v-else class="chev" viewBox="0 0 12 8"><path d="M1 1l5 5 5-5" /></svg>
    <transition name="fade">
      <ul v-if="open" class="menu" :class="{ up: dropUp }" @click.stop>
        <li v-for="o in options" :key="o.value" :class="{ active: o.value === modelValue }" @click="pick(o)">
          <span class="l">{{ o.label }}</span>
          <span v-if="o.desc" class="d">{{ o.desc }}</span>
        </li>
      </ul>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  modelValue: [String, Number],
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '请选择' },
  variant: { type: String, default: 'box' }, // box | compact | scheme
  dropUp: Boolean,
  disabled: Boolean,
})
const emit = defineEmits(['update:modelValue', 'change'])
const open = ref(false)
const root = ref(null)
const current = computed(() => props.options.find((o) => o.value === props.modelValue))

function toggle() {
  if (props.disabled) return
  open.value = !open.value
}
function pick(o) {
  open.value = false
  emit('update:modelValue', o.value)
  emit('change', o.value)
}
const close = (e) => { if (root.value && !root.value.contains(e.target)) open.value = false }
onMounted(() => document.addEventListener('click', close))
onBeforeUnmount(() => document.removeEventListener('click', close))
</script>

<style scoped>
.sel {
  position: relative;
  height: 40px;
  display: flex;
  align-items: center;
  padding: 0 34px 0 18px;
  background: linear-gradient(180deg, rgba(14, 40, 78, 0.92), rgba(8, 24, 48, 0.92));
  border: 1px solid rgba(79, 190, 255, 0.55);
  box-shadow: inset 0 0 10px rgba(47, 123, 255, 0.25);
  color: var(--text-0);
  font-size: 16px;
  font-weight: 700;
  font-style: italic;
  letter-spacing: 1px;
  cursor: pointer;
  pointer-events: auto;
}
.sel:hover { border-color: var(--cyan); box-shadow: inset 0 0 12px rgba(79, 210, 255, 0.35), 0 0 8px rgba(79, 210, 255, 0.3); }
.sel.disabled { opacity: 0.5; cursor: not-allowed; }
.sel .val { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chev { position: absolute; right: 12px; top: 50%; width: 14px; height: 10px; transform: translateY(-50%); }
.chev path { fill: none; stroke: var(--cyan); stroke-width: 2; }
.open .chev { transform: translateY(-50%) rotate(180deg); }

.sel.compact { height: 36px; font-size: 15px; padding: 0 30px 0 12px; justify-content: center; font-style: normal; }
.sel.scheme {
  height: 40px;
  padding: 0 40px 0 20px;
  font-style: normal;
  font-size: 16px;
  background: linear-gradient(180deg, rgba(10, 30, 60, 0.95), rgba(14, 44, 86, 0.95));
  border: 1px solid rgba(79, 210, 255, 0.7);
}
.chev.tri { width: 12px; height: 8px; }
.chev.tri path { fill: var(--lime); stroke: none; filter: drop-shadow(0 0 3px var(--lime)); }

.menu {
  position: absolute;
  left: -1px;
  right: -1px;
  top: calc(100% + 4px);
  z-index: 50;
  margin: 0;
  padding: 4px 0;
  list-style: none;
  background: rgba(6, 20, 40, 0.97);
  border: 1px solid var(--line-strong);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5), 0 0 12px rgba(79, 210, 255, 0.2);
  max-height: 360px;
  overflow-y: auto;
  min-width: 100%;
  width: max-content;
  max-width: 420px;
}
.menu.up { top: auto; bottom: calc(100% + 4px); }
.menu li {
  padding: 7px 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-style: normal;
  cursor: pointer;
}
.menu li .l { font-size: 15px; font-weight: 600; color: var(--text-0); }
.menu li .d { font-size: 12px; font-weight: 400; color: var(--text-2); letter-spacing: 0; }
.menu li:hover { background: rgba(47, 123, 255, 0.25); }
.menu li.active { background: linear-gradient(90deg, rgba(79, 210, 255, 0.35), rgba(79, 210, 255, 0.05)); }
.menu li.active .l { color: var(--cyan); }
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
