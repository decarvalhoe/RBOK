module.exports = {
  __esModule: true,
  default: {
    call: () => undefined,
    Value: function Value(initial) {
      this.value = initial;
    },
  },
  Easing: { linear: () => 0 },
  useSharedValue: (initial) => ({ value: initial }),
  useAnimatedStyle: (factory) => factory(),
  withTiming: (value) => value,
};
