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
# E:T Ratio 입력 (7개)
et_input = st.sidebar.text_input("행별 E:T Ratio (위/아래 각각 적용할 행 순서대로, 콤마 분리)", "0, 2.5, 5, 10, 20, 40, 80")
et_ratios = [float(x.strip()) for x in et_input.split(",")]

# 암세포별 열 매핑 설정 
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
    rows_list = []
    # 1. 반복구(Replicate) 데이터를 개별적으로 저장
    for r_idx, et in enumerate(et_list):
        for cell_name, cols in cell_map.items():
            for rep_idx, col in enumerate(cols):
                val = data_block[r_idx, col - 1] # 0-based 인덱스 적용
                rows_list.append({
                    "ET_Ratio": et,
                    "Cancer_Cell": cell_name,
                    "Replicate": rep_idx + 1, # 1, 2, 3...
                    "Value": val
                })
    df = pd.DataFrame(rows_list)
    
    # 2. 각 암세포별 ET_Ratio가 0인 3반복 데이터의 "평균" 구하기
    df_et_0 = df[df["ET_Ratio"] == 0]
    et_0_means = df_et_0.groupby("Cancer_Cell")["Value"].mean().to_dict()
    
    # 3. 개별 데이터를 ET_Ratio 0 평균값으로 나누어 Normalization 수행
    df["Normalized_Value"] = df.apply(
        lambda row: row["Value"] / et_0_means[row["Cancer_Cell"]] if et_0_means.get(row["Cancer_Cell"], 0) != 0 else np.nan, 
        axis=1
    )
    
    # 4. 암세포 이름과 반복수를 결합하여 새로운 열 이름 생성 (예: SNU2491_1, SNU2491_2...)
    df["Col_Name"] = df["Cancer_Cell"] + "_" + df["Replicate"].astype(str)
    
    # 5. 최종 출력 형태로 피벗 (평균 내지 않고 각 반복구를 개별 열로 배치)
    df_pivot = df.pivot_table(
        index="ET_Ratio", 
        columns="Col_Name", 
        values="Normalized_Value", 
        aggfunc="first" 
    )
    
    # 6. 보기 좋게 열 순서 정렬 (입력한 암세포 순서대로 1, 2, 3 배치)
    col_order = []
    for cell in cell_map.keys():
        for rep_idx in range(len(cell_map[cell])):
            col_order.append(f"{cell}_{rep_idx + 1}")
    
    # 존재하는 열만 필터링 후 적용
    col_order = [c for c in col_order if c in df_pivot.columns]
    df_pivot = df_pivot[col_order]
    
    # 입력한 ET Ratio 순서대로 행 정렬
    df_pivot = df_pivot.reindex(et_list)
    return df_pivot

# 2. 데이터 처리 및 메인 화면 디스플레이
if uploaded_file is not None:
    # 8줄을 넘어가는 ET Ratio 입력 방지
    if len(et_ratios) > 8:
        st.error("E:T Ratio는 위쪽/아래쪽 각각 최대 8개의 행까지만 매핑 가능합니다.")
    else:
        try:
            # 엑셀 파일 읽기
            df_raw = pd.read_excel(uploaded_file, header=None)
            
            # 플레이트 Readout 데이터 블록 전체 추출 (33행~48행, B열~Z열)
            plate_data = df_raw.iloc[32:48, 2:26].to_numpy(dtype=float)
            
            # ✨수정된 부분✨: 입력한 ET Ratio 개수(7개)만큼만 위/아래 블록에서 행을 잘라서 가져옴
            num_et = len(et_ratios)
            top_block = plate_data[0:num_et, :]         # 위쪽 7줄 (Row A~G)
            bottom_block = plate_data[8:8+num_et, :]    # 아래쪽 7줄 (Row I~O)
            
            # 데이터 분석 수행
            df_top_res = process_nk_data(top_block, et_ratios, cancer_cells)
            df_bottom_res = process_nk_data(bottom_block, et_ratios, cancer_cells)
            
            # 결과 화면 출력
            st.subheader(f"📊 {nk_top} 분석 결과 (위쪽 절반)")
            st.dataframe(df_top_res.style.format("{:.4f}"))
            
            st.subheader(f"📊 {nk_bottom} 분석 결과 (아래쪽 절반)")
            st.dataframe(df_bottom_res.style.format("{:.4f}"))
            
            # 3. 엑셀 파일 다운로드 링크 생성
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
                file_name="NK_Screening_Normalized_Result_Replicates.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.success("데이터 처리가 완료되었습니다! 왼쪽 사이드바에서 결과 엑셀 파일을 다운로드하세요.")
            
        except Exception as e:
            st.error(f"파일을 처리하는 중 오류가 발생했습니다. 오차 원인: {e}")
else:
    st.info("왼쪽 사이드바에서 플레이트 Readout 엑셀 파일을 업로드해주세요.")
