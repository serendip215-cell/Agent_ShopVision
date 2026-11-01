const FONT_FAMILY =
  'Manrope, "HarmonyOS Sans SC", "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'

export const antdTheme = {
  token: {
    colorPrimary: '#5FA8B0',
    colorInfo: '#5FA8B0',
    colorSuccess: '#3E8E68',
    colorWarning: '#B97A52',
    colorError: '#B4534F',
    colorBgLayout: '#FAFBFC',
    colorBgContainer: '#FFFFFF',
    colorBgElevated: '#FFFFFF',
    colorText: '#2F353A',
    colorTextSecondary: '#6B7280',
    colorTextTertiary: '#8A9299',
    colorBorder: '#ECEFF1',
    colorBorderSecondary: '#F1F3F5',
    colorSplit: '#F1F3F5',
    colorFillAlter: '#F7FAFA',
    colorFillSecondary: '#F3F7F8',
    borderRadius: 12,
    borderRadiusLG: 18,
    borderRadiusSM: 8,
    controlHeight: 42,
    fontSize: 14,
    fontFamily: FONT_FAMILY,
    boxShadow: '0 12px 32px rgba(47, 53, 58, 0.06)',
    boxShadowSecondary: '0 18px 48px rgba(47, 53, 58, 0.10)',
    wireframe: false,
  },
  components: {
    Layout: {
      bodyBg: '#FAFBFC',
      headerBg: '#FFFFFF',
      siderBg: '#FFFFFF',
    },
    Button: {
      borderRadius: 12,
      controlHeight: 42,
      primaryShadow: 'none',
      defaultShadow: 'none',
      fontWeight: 600,
    },
    Card: {
      borderRadiusLG: 18,
      paddingLG: 24,
    },
    Input: {
      borderRadius: 12,
      activeShadow: '0 0 0 4px rgba(95, 168, 176, 0.12)',
    },
    Select: {
      borderRadius: 12,
      optionSelectedBg: '#DDEFEF',
    },
    Slider: {
      trackBg: '#5FA8B0',
      trackHoverBg: '#4E969E',
      handleColor: '#5FA8B0',
      handleActiveColor: '#4E969E',
      railBg: '#ECEFF1',
      railHoverBg: '#E2E8EA',
    },
    Tag: {
      borderRadiusSM: 999,
      defaultBg: '#F3F7F8',
      defaultColor: '#4E5A60',
    },
    Table: {
      headerBg: '#F7FAFA',
      headerColor: '#6B7280',
      rowHoverBg: '#F7FBFC',
      borderColor: '#F1F3F5',
      headerBorderColor: '#F1F3F5',
    },
    Drawer: {
      colorBgElevated: '#FFFFFF',
    },
    Segmented: {
      trackBg: '#F3F7F8',
      itemSelectedBg: '#FFFFFF',
      itemSelectedColor: '#2F353A',
    },
    Progress: {
      defaultColor: '#5FA8B0',
      remainingColor: '#EFF4F5',
    },
    Upload: {
      colorFillAlter: '#FBFDFD',
    },
    Message: {
      contentBg: '#FFFFFF',
    },
  },
}
