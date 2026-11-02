const FONT_FAMILY =
  'Manrope, "HarmonyOS Sans SC", "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'

export const antdTheme = {
  token: {
    colorPrimary: '#4F46E5',
    colorInfo: '#4F46E5',
    colorSuccess: '#189A58',
    colorWarning: '#B45309',
    colorError: '#D64545',
    colorBgLayout: '#F4F4F6',
    colorBgContainer: '#FFFFFF',
    colorBgElevated: '#FFFFFF',
    colorText: '#1C1C21',
    colorTextSecondary: '#4B4B53',
    colorTextTertiary: '#85858D',
    colorBorder: '#E3E3E8',
    colorBorderSecondary: '#ECECF0',
    colorSplit: '#ECECF0',
    colorFillAlter: '#F9F9FB',
    colorFillSecondary: '#F1F1F4',
    borderRadius: 0,
    borderRadiusLG: 0,
    borderRadiusSM: 0,
    borderRadiusXS: 0,
    controlHeight: 42,
    fontSize: 14,
    fontFamily: FONT_FAMILY,
    boxShadow: '0 12px 32px rgba(20, 22, 30, 0.06)',
    boxShadowSecondary: '0 18px 48px rgba(20, 22, 30, 0.10)',
    wireframe: false,
  },
  components: {
    Layout: {
      bodyBg: '#F4F4F6',
      headerBg: '#FFFFFF',
      siderBg: '#FFFFFF',
    },
    Button: {
      borderRadius: 0,
      controlHeight: 42,
      primaryShadow: 'none',
      defaultShadow: 'none',
      fontWeight: 600,
    },
    Card: {
      borderRadiusLG: 0,
      paddingLG: 24,
    },
    Input: {
      borderRadius: 0,
      activeShadow: '0 0 0 4px rgba(79, 70, 229, 0.12)',
    },
    Select: {
      borderRadius: 0,
      optionSelectedBg: '#EEEDFD',
    },
    Slider: {
      trackBg: '#4F46E5',
      trackHoverBg: '#4338CA',
      handleColor: '#4F46E5',
      handleActiveColor: '#4338CA',
      railBg: '#E3E3E8',
      railHoverBg: '#D9D9E0',
    },
    Tag: {
      borderRadiusSM: 0,
      defaultBg: '#F1F1F4',
      defaultColor: '#4B4B53',
    },
    Table: {
      headerBg: '#F9F9FB',
      headerColor: '#85858D',
      rowHoverBg: '#FAFAFB',
      borderColor: '#ECECF0',
      headerBorderColor: '#ECECF0',
    },
    Drawer: {
      colorBgElevated: '#FFFFFF',
    },
    Segmented: {
      trackBg: '#E6E6EB',
      itemSelectedBg: '#FFFFFF',
      itemSelectedColor: '#1C1C21',
    },
    Progress: {
      defaultColor: '#4F46E5',
      remainingColor: '#EFF0F3',
    },
    Upload: {
      colorFillAlter: '#FAFAFB',
    },
    Message: {
      contentBg: '#FFFFFF',
    },
  },
}
