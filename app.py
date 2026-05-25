import streamlit as st
import pandas as pd
import numpy as np
import io

st.set_page_config(page_title="NK 세포 스크리닝 데이터 정규화 툴", layout="wide")

st.title("🧪 NK 세포 스크리닝 데이터 자동 정규화 툴")
st.write("플레이트 Readout 엑셀 파일을 업로드하면 설정된 플레이트 맵에 따라 자동으로 E:T Ratio 0 기준 정규화를 수행하고 결과 파일을 생성합니다.")

# 1. 사이드바 및 입력창 설정
st.sidebar.header("📋 실험 정보 입력")
uploaded_file = st.sidebar.file_uploader("엑셀 파일 업로드 (.xlsx)", type=["xlsx"])

nk_top = st.sidebar.text_input("위쪽 절반 NK 세포 이름 (Row A~H)", "NK_Top")
nk_bottom = st.sidebar.text_input("아래쪽 절반 NK 세포 이름 (Row I~P)", "NK_Bottom")

st.sidebar.subheader("⚙️ 플레이트 맵 설정")
# E:T Ratio 입력 (위/아래 절반 각각 8개 행에 대응)
et_input = st.sidebar.text_input("행별 E:T Ratio (위/아래 각각 8개 행 순서대로, 콤마 분리)", "0, 2.5, 5, 10, 20, 40, 80")
et_ratios = [float(x.strip()) for x in et_input.split(",")]

# 암세포별 열 매핑 설정 (기본값 설정)
default_mapping = """SNU2491: 3,4,5
SNU324: 7,8,9
MIAPaCa2: 11,12,13
PANC1: 15,16,17
BME: 19,20,21"""
mapping_text = st.sidebar.text_area("암세포별 플레이트 열(Column) 매핑", default_mapping)

# 암세포 매핑 텍스트 파싱
cancer_cells = {}
try:
    for line in mapping_text.strip().split("\n"):
        if ":" in line:
            cell_name, cols_str = line.split(":")
            cols = [int(x.strip()) for x in cols_str.split(",")]
            cancer_cells[cell_name.strip()] = cols
except Exception as e:
    st.error("암세포 열 매핑 입력 형식이 올바르지 않습니다. '암세포명: 열,열,열' 형식으로 입력해주세요.")

# 데이터 처리 함수
def process_nk_data(data_block, et_list, cell_map):
    # data_block: 8 rows x 24 cols numpy array
    # 1. 롱포맷 데이터프레임 구조 생성
    rows_list = []
    for r_idx, et in enumerate(et_list):
        for cell_name, cols in cell_map.items():
            for col in cols:
                # 플레이트 열 번호(1~24)를 0-based 인덱스로 변환
                val = data_block[r_idx, col - 1]
                rows_list.append({
                    "ET_Ratio": et,
                    "Cancer_Cell": cell_name,
                    "Value": val
                })
    df = pd.DataFrame(rows_list)
    
    # 2. 각 암세포별 ET_Ratio가 0인 데이터의 평균 구하기
    df_et_0 = df[df["ET_Ratio"] == 0]
    et_0_means = df_et_0.groupby("Cancer_Cell")["Value"].mean().to_dict()
    
    # 3. ET_Ratio 0 평균값으로 나누어 Normalization 수행
    df["Normalized_Value"] = df.apply(
        lambda row: row["Value"] / et_0_means[row["Cancer_Cell"]] if et_0_means.get(row["Cancer_Cell"], 0) != 0 else np.nan, 
        axis=1
    )
    
    # 4. 최종 출력 형태로 피벗 (행: ET_Ratio, 열: 암세포별 평균값)
    # 반복구 실험 데이터의 평균을 내어 최종 리포트 작성
    df_pivot = df.pivot_table(
        index="ET_Ratio", 
        columns="Cancer_Cell", 
        values="Normalized_Value", 
        aggfunc="mean"
    )
    
    # 입력한 ET Ratio 순서대로 정렬 보장
    df_pivot = df_pivot.reindex(et_list)
    return df_pivot

# 2. 데이터 처리 및 메인 화면 디스플레이
if uploaded_file is not None:
    if len(et_ratios) != 8:
        st.error("E:T Ratio는 위쪽/아래쪽 각각 8개의 행에 매핑되어야 하므로 정확히 8개의 값을 입력해야 합니다.")
    else:
        try:
            # 엑셀 파일 읽기 (헤더 없이 로우 데이터로 로드)
            df_raw = pd.read_excel(uploaded_file, header=None)
            
            # 33행부터 49행은 파인썬 인덱스 기준으로 32:49 (49행 미포함 시 17개 행, 보통 16개 행 데이터 + 1개 헤더 구조)
            # 플레이트 Readout 데이터 블록 추출 (B열~Z열은 파인썬 인덱스 1:26)
            # 보통 B열은 행 라벨(A~P), C열~Z열이 1~24열 데이터에 해당하므로 2:26으로 슬라이싱합니다.
            plate_data = df_raw.iloc[32:48, 2:26].to_numpy(dtype=float)
            
            # 위 절반 (Row A~H, 0~8행), 아래 절반 (Row I~P, 8~16행) 분리
            top_block = plate_data[0:8, :]
            bottom_block = plate_data[8:16, :]
            
            # 데이터 분석 수행
            df_top_res = process_nk_data(top_block, et_ratios, cancer_cells)
            df_bottom_res = process_nk_data(bottom_block, et_ratios, cancer_cells)
            
            # 결과 화면 출력
            st.subheader(f"📊 {nk_top} 분석 결과 (위쪽 절반)")
            st.dataframe(df_top_res.style.format("{:.4f}"))
            
            st.subheader(f"📊 {nk_bottom} 분석 결과 (아래쪽 절반)")
            st.dataframe(df_bottom_res.style.format("{:.4f}"))
            
            # 3. 엑셀 파일 다운로드 링크 생성 (메모리 버퍼 사용)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_top_res.to_excel(writer, sheet_name=nk_top)
                df_bottom_res.to_excel(writer, sheet_name=nk_bottom)
            
            processed_data = output.getvalue()
            
            st.sidebar.markdown("---")
            st.sidebar.subheader("💾 결과 다운로드")
            st.sidebar.download_button(
                label="정리된 엑셀 파일 다운로드",
                data=processed_data,
                file_name="NK_Screening_Normalized_Result.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.success("데이터 처리가 완료되었습니다! 왼쪽 사이드바에서 결과 엑셀 파일을 다운로드하세요.")
            
        except Exception as e:
            st.error(f"파일을 처리하는 중 오류가 발생했습니다. 엑셀 파일의 데이터 위치(33행~49행, B~Z열)가 맞는지 다시 확인해주세요. 오차 원인: {e}")
else:
    st.info("왼쪽 사이드바에서 플레이트 Readout 엑셀 파일을 업로드해주세요.")
